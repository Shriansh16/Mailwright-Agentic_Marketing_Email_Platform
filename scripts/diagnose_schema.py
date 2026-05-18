from dotenv import load_dotenv

load_dotenv()

import json
from pathlib import Path
import pprint


def find_column_contents(data, path="", columns_found=None):
    """Recursively finds all 'columns' arrays and prints their contents."""
    if columns_found is None:
        columns_found = []

    if isinstance(data, dict):
        if "columns" in data and isinstance(data["columns"], list):
            print(f"--- Found 'columns' array at path: {path} ---")
            for i, col in enumerate(data["columns"]):
                print(f"  - Column {i} contents:")
                pprint.pprint(col)
                print("-" * 20)
            columns_found.append(data["columns"])

        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            find_column_contents(value, new_path, columns_found)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]"
            find_column_contents(item, new_path, columns_found)


def main():
    """Main function to run the diagnostic."""
    project_root = Path(__file__).parent.parent
    template_path = project_root / "templates" / "abandoned-cart.json"

    print(f"--- Running Deep Diagnostic on {template_path.name} ---")
    with open(template_path, "r", encoding="utf-8") as f:
        template_data = json.load(f)

    json_to_process = template_data.get("json_data", {})

    print("\\n--- Finding all column structures ---")
    find_column_contents(json_to_process)

    print("\\n--- Diagnostic Complete ---")


if __name__ == "__main__":
    main()
