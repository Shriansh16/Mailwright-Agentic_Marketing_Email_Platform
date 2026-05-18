from dotenv import load_dotenv

load_dotenv()

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from PIL import Image
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    ViTImageProcessor,
    ViTModel,
    pipeline,
)

from mailwright.templates.store import TemplateStore


class NLP:
    """Natural Language Processing for template analysis"""

    def __init__(self):
        # Check for GPU availability
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        # Initialize NER pipeline with GPU support
        self.ner = pipeline(
            "ner",
            model="dbmdz/bert-large-cased-finetuned-conll03-english",
            device=0 if self.device == "cuda" else -1,
        )

        # Initialize sentiment/tone classifier
        self.tokenizer = AutoTokenizer.from_pretrained(
            "j-hartmann/emotion-english-distilroberta-base"
        )
        self.tone_classifier = AutoModelForSequenceClassification.from_pretrained(
            "j-hartmann/emotion-english-distilroberta-base"
        ).to(self.device)

        # Initialize sentence transformer for embeddings
        self.embedder = pipeline(
            "feature-extraction",
            model="sentence-transformers/all-mpnet-base-v2",
            device=0 if self.device == "cuda" else -1,
        )

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract named entities from text"""
        entities = self.ner(text)
        merged_entities = []
        current = None

        for entity in entities:
            if (
                current
                and entity["entity"] == current["entity"]
                and entity["start"] == current["end"]
            ):
                current["word"] += " " + entity["word"]
                current["end"] = entity["end"]
            else:
                if current:
                    merged_entities.append(current)
                current = entity.copy()

        if current:
            merged_entities.append(current)

        return merged_entities

    def classify_tone(self, text: str) -> Dict[str, float]:
        """Classify the emotional tone of the text"""
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=512
        )
        # Move inputs to GPU if available
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        outputs = self.tone_classifier(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

        return {
            label: prob.item()
            for label, prob in zip(
                self.tone_classifier.config.id2label.values(), probs[0]
            )
        }

    def generate_embedding(
        self, text: str, entities: List[Dict], tone: Dict[str, float]
    ) -> List[float]:
        """Generate embedding combining text, entities, and tone features"""
        text_embedding = self.embedder(text)[0][0]

        entity_text = " ".join([f"{e['word']}({e['entity']})" for e in entities])
        tone_text = " ".join([f"{k}:{v:.2f}" for k, v in tone.items()])

        entity_embedding = self.embedder(entity_text)[0][0]
        tone_embedding = self.embedder(tone_text)[0][0]

        combined = [
            t + e + n
            for t, e, n in zip(text_embedding, entity_embedding, tone_embedding)
        ]
        return combined


class Images:
    """Image analysis for template-related visuals"""

    def __init__(self):
        # Check for GPU availability
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Images module using device: {self.device}")

        self.processor = ViTImageProcessor.from_pretrained(
            "google/vit-base-patch16-224"
        )
        # Use ignore_mismatched_sizes=True to suppress the warning about uninitialized weights
        self.model = ViTModel.from_pretrained(
            "google/vit-base-patch16-224",
            add_pooling_layer=False,  # Disable the pooling layer since we don't need it
            ignore_mismatched_sizes=True,
        ).to(self.device)

    def find_related_images(
        self, entities: List[Dict], templates_dir: str
    ) -> List[str]:
        """Find images related to extracted entities based on filename similarity"""
        image_files = []
        for root, _, files in os.walk(templates_dir):
            for file in files:
                if file.lower().endswith((".png", ".jpg", ".jpeg")):
                    for entity in entities:
                        if entity["word"].lower() in file.lower():
                            image_files.append(os.path.join(root, file))
        return image_files

    def generate_embedding(self, image_path: str) -> Optional[List[float]]:
        """Generate embedding for an image"""
        try:
            image = Image.open(image_path)
            inputs = self.processor(images=image, return_tensors="pt")
            # Move inputs to GPU if available
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Set output_hidden_states=True to get all hidden states
            outputs = self.model(**inputs, output_hidden_states=True)

            # Use the [CLS] token from the last hidden state as the embedding
            # This is a common approach for image embeddings with ViT
            embedding = outputs.last_hidden_state[:, 0].squeeze().detach()

            # Move result back to CPU for conversion to list
            return embedding.cpu().tolist()
        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            return None


class Content:
    """Unified content analysis class for text and images"""

    TEMPLATES_DATA_DIR = "data/templates"

    def __init__(self, store: "TemplateStore"):
        self.nlp = NLP()
        self.images = Images()
        self.store = store

    def add_template(self, template_id: str, template_data: Dict):
        """Add template to store with content analysis"""
        # Combine relevant text for analysis
        text = f"{template_data['subject']} {template_data['body']}"

        # Analyze template content
        embedding, metadata = self.analyze_template(text, "data/templates")

        # Store template with analysis results
        self.store.add_template(
            template_id=template_id,
            embedding=embedding,
            metadata={**template_data, **metadata},
        )

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyze text content returning entities, tone, and embedding"""
        entities = self.nlp.extract_entities(text)
        tone = self.nlp.classify_tone(text)
        embedding = self.nlp.generate_embedding(text, entities, tone)

        return {"entities": entities, "tone": tone, "embedding": embedding}

    def analyze_images(
        self, entities: List[Dict], templates_dir: str
    ) -> List[Dict[str, Any]]:
        """Find and analyze related images"""
        image_paths = self.images.find_related_images(entities, templates_dir)
        results = []

        for path in image_paths:
            embedding = self.images.generate_embedding(path)
            if embedding:
                results.append({"path": path, "embedding": embedding})

        return results

    def analyze_template(
        self, text: str, templates_dir: str
    ) -> Tuple[List[float], Dict[str, Any]]:
        """Analyze both text and related images for a template"""
        # Analyze text
        text_analysis = self.analyze_text(text)

        # Find and analyze related images
        image_analysis = self.analyze_images(text_analysis["entities"], templates_dir)

        # Combine text and image embeddings if available
        combined_embedding = text_analysis["embedding"]
        if image_analysis:
            # Determine device for computation
            device = "cuda" if torch.cuda.is_available() else "cpu"

            # Convert to tensor and move to appropriate device
            text_tensor = torch.tensor(combined_embedding, device=device)

            # Average the image embeddings
            image_tensors = [
                torch.tensor(img["embedding"], device=device) for img in image_analysis
            ]
            image_embedding = torch.mean(torch.stack(image_tensors), dim=0)

            # Combine with text embedding (simple addition for now)
            combined_embedding = (text_tensor + image_embedding).cpu().tolist()

        metadata = {
            "entities": text_analysis["entities"],
            "tone": text_analysis["tone"],
            "related_images": [img["path"] for img in image_analysis],
        }

        return combined_embedding, metadata

    def load_template_from_file(self, template_path: str) -> None:
        """
        Load a template from a JSON file and add it to the store

        Args:
            template_path: Path to the JSON template file
        """
        try:
            # Read the JSON file
            with open(template_path) as f:
                template_data = json.loads(f.read())

            print("Raw template data:", json.dumps(template_data, indent=2))

            # Extract template ID from filename
            template_id = Path(template_path).stem
            print(f"Template ID: {template_id}")

            # Prepare template data
            processed_template = {
                "subject": template_data.get("short_description", ""),
                "body": template_data.get("description", ""),
                "categories": template_data.get("categories", []),
                "collections": template_data.get("collections", ""),
                "designer": template_data.get("designer", {}),
            }
            print("Processed template:", json.dumps(processed_template, indent=2))

            # Add template to store
            print("About to add template to store...")
            self.add_template(template_id, processed_template)
            print("Template added successfully")

        except Exception as e:
            print(f"Error loading template from {template_path}: {e}")
            # Print full stack trace for debugging
            import traceback

            traceback.print_exc()

    def get_template(self, template_id: str) -> Optional[Dict]:
        """
        Retrieve a template from the store

        Args:
            template_id: ID of the template to retrieve

        Returns:
            Template data if found, None otherwise
        """
        return self.store.get_template(template_id)


if __name__ == "__main__":  # testing
    import sys

    # Initialize the store and content analyzer
    store = TemplateStore()
    content = Content(store)

    # Get template filename from command line argument or use default
    template_filename = sys.argv[1] if len(sys.argv) > 1 else "12-months-of-data"

    # Construct full template path
    template_path = f"{Content.TEMPLATES_DATA_DIR}/{template_filename}.json"

    print(f"\nLoading template from: {template_path}")
    content.load_template_from_file(template_path)

    # Verify the template was loaded
    template = content.get_template(template_filename)
    if template:
        print("\nSuccessfully loaded template:")
        print(f"ID: {template['template_id']}")
        print(f"Metadata: {template['metadata']}")

        # Test similarity search
        print("\nFinding similar templates...")
        similar = store.find_similar(template["embedding"])
        print("\nSimilar templates:")
        for result in similar:
            print(f"Template: {result['template_id']}")
            print(f"Score: {result['score']}")
            print(f"Metadata: {result['metadata']}")
    else:
        print(f"\nFailed to load template: {template_filename}!")
