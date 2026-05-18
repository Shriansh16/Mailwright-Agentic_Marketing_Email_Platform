from dotenv import load_dotenv

load_dotenv()

import os
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import psycopg2
import torch
from psycopg2.extras import DictCursor, Json
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from umap import UMAP


class TemplateStore:
    def __init__(self, db_path: str = "data/vector_store"):
        # Create directory if it doesn't exist
        os.makedirs(db_path, exist_ok=True)

        # Database connection parameters - these should come from environment or config
        self.db_params = {
            "dbname": "templates_db",
            "user": "postgres",
            "password": os.getenv("POSTGRES_PASSWORD", "pgvector!"),
            "host": "localhost",
            "port": "5432",
        }

        # Initialize the database
        self._init_database()

    def _init_database(self):
        """Initialize the database schema if it doesn't exist"""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()

        try:
            # Check if pg_vector extension is installed
            cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
            if cursor.fetchone() is None:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Create templates table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    template_id TEXT PRIMARY KEY,
                    embedding VECTOR(768),
                    metadata JSONB
                )
            """)

            # Create index for vector similarity search
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS templates_embedding_idx 
                ON templates USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error initializing database: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def add_template(self, template_id: str, embedding: List[float], metadata: Dict):
        """Add template embedding and metadata to store"""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()

        try:
            # Convert embedding to proper format
            embedding_array = np.array(embedding)

            # Insert or update the template
            cursor.execute(
                """
                INSERT INTO templates (template_id, embedding, metadata)
                VALUES (%s, %s, %s)
                ON CONFLICT (template_id) 
                DO UPDATE SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata
            """,
                (template_id, embedding_array.tolist(), Json(metadata)),
            )

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error adding template: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def find_similar(self, embedding: List[float], limit: int = 2) -> List[Dict]:
        """Find similar templates based on embedding"""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor(cursor_factory=DictCursor)

        try:
            # Convert embedding to proper format and cast to vector in SQL
            embedding_array = np.array(embedding)

            # Query for similar templates, properly casting the input array to vector type
            cursor.execute(
                """
                SELECT template_id, metadata, 
                       1 - (embedding <=> %s::vector) as score
                FROM templates
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """,
                (embedding_array.tolist(), embedding_array.tolist(), limit),
            )

            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "template_id": row["template_id"],
                        "metadata": row["metadata"],
                        "score": float(row["score"]),
                    }
                )

            return results
        except Exception as e:
            print(f"Error finding similar templates: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Retrieve a template by ID"""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor(cursor_factory=DictCursor)

        try:
            cursor.execute(
                """
                SELECT template_id, embedding, metadata
                FROM templates
                WHERE template_id = %s
            """,
                (template_id,),
            )

            result = cursor.fetchone()
            if result:
                return {
                    "template_id": result["template_id"],
                    "embedding": result["embedding"],
                    "metadata": result["metadata"],
                }
            return None
        except Exception as e:
            print(f"Error retrieving template: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all_templates(self) -> List[Dict]:
        """Get all templates in store"""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor(cursor_factory=DictCursor)

        try:
            cursor.execute("""
                SELECT template_id, embedding, metadata
                FROM templates
            """)

            templates = []
            for row in cursor.fetchall():
                templates.append(
                    {
                        "template_id": row["template_id"],
                        "embedding": row["embedding"],
                        "metadata": row["metadata"],
                    }
                )

            return templates
        except Exception as e:
            print(f"Error retrieving all templates: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def index_templates_directory(
        self,
        templates_dir: str = "data/templates",
        progress_file: str = "data/indexing_progress.json",
        batch_size: int = 10,
    ) -> Dict:
        """
        Index all templates in the specified directory, making the process resumable.

        Args:
            templates_dir: Directory containing template JSON files
            progress_file: File to track indexing progress
            batch_size: Number of templates to process in each batch

        Returns:
            Dict with indexing statistics
        """
        import json
        from pathlib import Path

        from mailwright.templates.content import Content

        # Create Content analyzer without circular dependency
        content_analyzer = Content(self)

        # Initialize tracking data
        indexed_files = set()
        failed_files = {}

        # Load progress if exists
        if os.path.exists(progress_file):
            try:
                with open(progress_file) as f:
                    progress = json.load(f)
                    indexed_files = set(progress.get("indexed", []))
                    failed_files = progress.get("failed", {})
                    print(
                        f"Resuming indexing. Already indexed: {len(indexed_files)} templates"
                    )
            except Exception as e:
                print(f"Error loading progress file: {e}. Starting fresh.")

        # Get all template files
        template_paths = []
        for file_path in Path(templates_dir).glob("**/*.json"):
            template_paths.append(str(file_path))

        total_files = len(template_paths)
        newly_indexed = 0
        newly_failed = 0

        # Process files in batches
        for i in range(0, len(template_paths), batch_size):
            batch = template_paths[i : i + batch_size]

            for template_path in batch:
                template_id = Path(template_path).stem

                # Skip already indexed files
                if template_id in indexed_files:
                    continue

                try:
                    # Load and index template
                    content_analyzer.load_template_from_file(template_path)
                    indexed_files.add(template_id)
                    newly_indexed += 1
                    print(
                        f"Indexed template {template_id} ({newly_indexed}/{total_files - len(indexed_files)})"
                    )

                    # Remove from failed if it was there
                    if template_id in failed_files:
                        del failed_files[template_id]

                except Exception as e:
                    failed_files[template_id] = str(e)
                    newly_failed += 1
                    print(f"Failed to index template {template_id}: {e}")

            # Save progress after each batch
            progress = {
                "indexed": list(indexed_files),
                "failed": failed_files,
                "total": total_files,
                "last_updated": str(Path(progress_file).stat().st_mtime)
                if os.path.exists(progress_file)
                else None,
            }

            with open(progress_file, "w") as f:
                json.dump(progress, f, indent=2)

        # Final stats
        return {
            "total_templates": total_files,
            "indexed_total": len(indexed_files),
            "newly_indexed": newly_indexed,
            "failed_total": len(failed_files),
            "newly_failed": newly_failed,
            "progress_file": progress_file,
        }

    def get_indexing_status(
        self, progress_file: str = "data/indexing_progress.json"
    ) -> Dict:
        """
        Get the current indexing status

        Args:
            progress_file: Path to the progress tracking file

        Returns:
            Dict with indexing status information
        """
        import json

        if not os.path.exists(progress_file):
            return {"status": "not_started", "message": "No indexing job has been run"}

        try:
            with open(progress_file) as f:
                progress = json.load(f)

            indexed_count = len(progress.get("indexed", []))
            failed_count = len(progress.get("failed", {}))
            total = progress.get("total", 0)

            if indexed_count + failed_count >= total:
                status = "complete"
            else:
                status = "in_progress"

            return {
                "status": status,
                "total_templates": total,
                "indexed_count": indexed_count,
                "failed_count": failed_count,
                "completion_percentage": round((indexed_count / total) * 100, 2)
                if total > 0
                else 0,
                "last_updated": progress.get("last_updated"),
            }
        except Exception as e:
            return {"status": "error", "message": f"Error reading progress file: {e}"}

    def delete_template(self, template_id: str) -> bool:
        """Delete a template by ID"""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                DELETE FROM templates
                WHERE template_id = %s
            """,
                (template_id,),
            )

            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print(f"Error deleting template: {e}")
            return False
        finally:
            cursor.close()
            conn.close()


class TemplateExplorer:
    def __init__(self, template_store: TemplateStore):
        """Initialize with a TemplateStore instance"""
        self.store = template_store
        self.dimensionality_reducers = {"pca": PCA, "tsne": TSNE, "umap": UMAP}

    def get_all_embeddings(self) -> Tuple[List[str], np.ndarray, Dict]:
        """Retrieve all template embeddings for analysis

        Returns:
            Tuple containing:
            - List of template IDs
            - Matrix of embeddings
            - Dictionary mapping template_id to metadata
        """
        templates = self.store.get_all_templates()
        ids = [t["template_id"] for t in templates]
        embeddings = np.array([t["embedding"] for t in templates])
        metadata = {t["template_id"]: t["metadata"] for t in templates}
        return ids, embeddings, metadata

    def reduce_dimensions(
        self,
        embeddings: np.ndarray,
        method: str = "tsne",
        dimensions: int = 2,
        **kwargs,
    ) -> np.ndarray:
        """Reduce embeddings to lower dimensions for visualization

        Args:
            embeddings: High-dimensional embedding matrix
            method: Dimensionality reduction method ('pca', 'tsne', 'umap')
            dimensions: Target dimensionality (usually 2 or 3 for visualization)
            **kwargs: Additional parameters for the reduction method

        Returns:
            Lower-dimensional representation of embeddings
        """
        if method not in self.dimensionality_reducers:
            raise ValueError(
                f"Method {method} not supported. Use one of {list(self.dimensionality_reducers.keys())}"
            )

        reducer_class = self.dimensionality_reducers[method]
        reducer = reducer_class(n_components=dimensions, **kwargs)
        return reducer.fit_transform(embeddings)

    def export_for_visualization(
        self, output_format: str = "csv", method: str = "tsne", dimensions: int = 3
    ) -> Union[str, Dict]:
        """Export embeddings in format suitable for visualization tools

        Args:
            output_format: Format to export ('csv', 'json', 'tensorboard')
            method: Dimensionality reduction method
            dimensions: Target dimensionality

        Returns:
            Path to exported file or data in requested format
        """
        ids, embeddings, metadata = self.get_all_embeddings()
        reduced_embeddings = self.reduce_dimensions(embeddings, method, dimensions)  # noqa: F841

        # Implementation would vary based on output_format
        # Return file path or data structure depending on format

    def cluster_templates(
        self, n_clusters: int = 5, method: str = "kmeans"
    ) -> Dict[str, int]:
        """Cluster templates based on embeddings

        Args:
            n_clusters: Number of clusters to create
            method: Clustering method ('kmeans', 'dbscan', etc.)

        Returns:
            Dictionary mapping template_id to cluster
        """
        ids, embeddings, _ = self.get_all_embeddings()
        # Implementation of clustering logic
        # Return mapping of template_id to cluster

    def find_outliers(self, contamination: float = 0.05) -> List[str]:
        """Find outlier templates that differ significantly from others

        Args:
            contamination: Expected proportion of outliers

        Returns:
            List of template_ids identified as outliers
        """
        # Implementation using isolation forest or other outlier detection


if __name__ == "__main__":
    if torch.cuda.is_available():
        print(f"CUDA device count: {torch.cuda.device_count()}")
        print(f"CUDA device name: {torch.cuda.get_device_name(0)}")

    # Test the store functionality
    store = TemplateStore("test_vector_store")

    # Test data
    test_template = {
        "template_id": "test1",
        "embedding": [0.1] * 768,  # Simple test embedding
        "metadata": {
            "body": "Test body text",
            "categories": [],
            "collections": "test collection",
            "designer": {
                "avatar_url": "",
                "description": "",
                "display_name": "Test Designer",
                "id": "test-designer",
                "short_description": "",
            },
            "subject": "Test subject",
        },
    }

    # Add test template
    store.add_template(
        test_template["template_id"],
        test_template["embedding"],
        test_template["metadata"],
    )

    # Test retrieval
    retrieved = store.get_template("test1")
    print("\nRetrieved template:")
    print(f"ID: {retrieved['template_id']}")
    print(f"Metadata: {retrieved['metadata']}")

    # Test similarity search
    similar = store.find_similar([0.1] * 768, limit=1)
    print("\nSimilarity search results:")
    for result in similar:
        print(f"Template: {result['template_id']}")
        print(f"Score: {result['score']}")
        print(f"Metadata: {result['metadata']}")

    # Clean up test data
    store.delete_template("test1")

    # Uncomment to run the indexing job
    # print("\nIndexing all templates in the corpus:")
    # results = store.index_templates_directory()
    # print(f"Indexing complete. Stats: {results}")
    # #
    # # # Get indexing status
    # status = store.get_indexing_status()
    # print(f"Current indexing status: {status}")
