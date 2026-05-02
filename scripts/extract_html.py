import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse

def extract_html_by_name(template_name: str, output_dir: Path):
    """
    Connects to the database, fetches the HTML for a given template,
    and saves it to a file.
    """
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in .env file.")
        return

    # Parse the database URL
    result = urlparse(db_url)
    dsn = (
        f"dbname={result.path[1:]} "
        f"user={result.username} "
        f"password={result.password} "
        f"host={result.hostname} "
        f"port={result.port}"
    )

    conn = None
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        cur.execute(
            "SELECT processed_html FROM rag_templates WHERE template_name = %s",
            (template_name,),
        )
        result = cur.fetchone()

        if result:
            html_content = result[0]
            output_path = output_dir / f"{template_name}.html"
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Successfully extracted HTML for '{template_name}' to '{output_path}'")
        else:
            print(f"Error: Template '{template_name}' not found in the database.")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).parent.parent
    OUTPUT_DIR = PROJECT_ROOT / "output"
    TEMPLATE_NAME = "wimbledon-sale-page"  # The template to extract
    extract_html_by_name(TEMPLATE_NAME, OUTPUT_DIR)
