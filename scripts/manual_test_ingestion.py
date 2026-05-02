"""
A manual test script to verify the output of the CorpusIngestionService.
"""

import json
from pathlib import Path
import pprint

# This script is now a self-contained debugger for the fingerprint logic.


def get_module_tag(module: dict) -> str:
    """Maps a JSON module to a simplified tag based on the 'type' key."""
    module_type_raw = module.get("type", "unknown")
    module_type = module_type_raw.split("-")[-1]

    print(
        f"    - Checking module: type_raw='{module_type_raw}', derived_type='{module_type}'"
    )

    if module_type in ["paragraph", "list", "text"]:
        return "[text]"
    if module_type == "title":
        return "[headline]"
    if module_type in ["button", "image", "divider", "social", "video"]:
        return f"[{module_type}]"

    print(f"    - Module type '{module_type}' did not match any known tags.")
    return ""


def main():
    """Main function to run the manual test."""
    project_root = Path(__file__).parent.parent
    template_path = project_root / "templates" / "abandoned-cart.json"

    print("--- STARTING LOGIC DEBUGGER ---")
    with open(template_path, "r", encoding="utf-8") as f:
        template_data = json.load(f)

    json_to_process = template_data.get("json_data", {})
    if not json_to_process:
        print("ERROR: 'json_data' key not found.")
        return

    # --- Start of the logic from _generate_structural_fingerprint ---
    fingerprint_parts = []

    print("\\n1. Accessing rows...")
    rows = json_to_process.get("page", {}).get("rows", [])
    print(f"   - Found {len(rows)} rows.")
    if not rows:
        print("   - EXITING: No rows found.")
        return

    for i, row in enumerate(rows):
        print(f"\\n2. Processing Row {i + 1}...")
        columns = row.get("columns", [])
        num_cols = len(columns)
        print(f"   - Found {num_cols} columns in this row.")

        if num_cols == 0:
            print("   - Skipping row because it has no columns.")
            continue

        row_tag = f"[{num_cols}-col]"
        row_parts = [row_tag]

        for j, column in enumerate(columns):
            print(f"\\n3. Processing Column {j + 1} in Row {i + 1}...")
            pprint.pprint(column.get("modules"))  # See the raw modules
            col_parts = []
            modules = column.get("modules", [])
            print(f"   - Found {len(modules)} modules in this column.")

            for k, module in enumerate(modules):
                print(f"   - Processing Module {k + 1}...")
                tag = get_module_tag(module)
                if tag:
                    print(f"     - SUCCESS: Got tag '{tag}'")
                    if tag not in col_parts:
                        col_parts.append(tag)
                    else:
                        print(f"     - Skipping duplicate tag '{tag}'")
                else:
                    print("     - FAILURE: No tag generated for this module.")

            if col_parts:
                print(f"   - Assembled column parts: {''.join(col_parts)}")
                row_parts.append("".join(col_parts))

        final_row_part = "".join(row_parts)
        print(f"   - Assembled row fingerprint: {final_row_part}")
        fingerprint_parts.append(final_row_part)

    final_fingerprint = " ".join(fingerprint_parts)
    print("\\n--- FINAL FINGERPRINT ---")
    print(final_fingerprint)
    print("\\n--- END OF DEBUGGER ---")


if __name__ == "__main__":
    main()
