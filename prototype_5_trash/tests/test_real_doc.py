"""
Detailed test of prototype_3 with real insurance document
"""

import json
import sys
from pathlib import Path
from core.document_accessor import DocumentAccessor


def load_document(doc_path: str):
    """Load JSON document"""
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading document: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_real_doc.py <document_path>")
        return

    doc_path = sys.argv[1]
    print("="*80)
    print(f"Detailed Analysis of: {Path(doc_path).name}")
    print("="*80)

    # Load document
    doc = load_document(doc_path)
    if doc is None:
        return

    # Initialize DocumentAccessor
    accessor = DocumentAccessor(doc)

    # 1. Find definition sections
    print("\n🔍 Step 1: Finding Definition Sections...")
    definition_sections = accessor.find_sections({
        "title_contains": ["명칭", "정의", "용어", "보험종목"]
    })

    if not definition_sections:
        print("  ❌ No definition sections found!")
        return

    print(f"  ✅ Found {len(definition_sections)} section(s)")

    # 2. Extract table content from the first definition section
    target_section = definition_sections[0]
    print(f"\n📊 Step 2: Extracting Table Content from Section [{target_section.index}]")
    print(f"  Section Title: {target_section.title}")

    table_contents = accessor.extract_content(target_section, content_type="table")

    if not table_contents:
        print("  ❌ No table content found!")
        return

    print(f"  ✅ Found {len(table_contents)} table(s)")

    # 3. Analyze first table
    first_table = table_contents[0]
    table_data = first_table.data

    print(f"\n📋 Step 3: Analyzing Table Structure...")
    print(f"  Table type: {type(table_data)}")

    if isinstance(table_data, dict):
        print(f"  Keys: {list(table_data.keys())}")

        table_elements = table_data.get("table_elements", [])
        print(f"  Total rows: {len(table_elements)}")

        if table_elements:
            print(f"\n  First element type: {type(table_elements[0])}")

            # Check if already parsed as dict
            if isinstance(table_elements[0], dict):
                print(f"  ✅ Table is already parsed as dict format!")
                print(f"\n  First 3 rows (dict format):")
                for i, row in enumerate(table_elements[:3], 1):
                    print(f"    Row {i}: {json.dumps(row, ensure_ascii=False)}")
            else:
                # cells format
                print(f"\n  First 5 rows (cells format):")
                for i, row in enumerate(table_elements[:5], 1):
                    if isinstance(row, dict):
                        cells = row.get("cells", [])
                        row_texts = [cell.get("text", "") for cell in cells]
                        print(f"    Row {i}: {row_texts}")

    # 4. Test rule-based extraction (simulate RuleExtractTool)
    print(f"\n🔧 Step 4: Simulating Rule-based Extraction...")

    header = None
    data = None

    if isinstance(table_data, dict):
        table_elements = table_data.get("table_elements", [])

        # Check format
        if table_elements and isinstance(table_elements[0], dict) and "cells" not in table_elements[0]:
            # Already parsed dict format (keys are column names)
            print(f"  Format: Pre-parsed dict (keys are column names)")

            # Extract header from keys
            header = list(table_elements[0].keys())
            print(f"  Header extracted from keys: {header}")

            # Extract data
            data = []
            for row in table_elements:
                row_data = [str(row.get(col, "")) for col in header]
                data.append(row_data)

            print(f"  Data rows extracted: {len(data)}")

        else:
            # cells format
            print(f"  Format: Cells format")
            data_rows = []
            for row in table_elements:
                cells = row.get("cells", [])
                if not cells:
                    continue

                # Filter comment rows
                first_cell = cells[0].get("text", "").strip()
                if first_cell.startswith(("※", "주:", "주)", "* ", "- ")):
                    print(f"    [FILTERED] Comment row: {first_cell}")
                    continue

                row_data = [cell.get("text", "").strip() for cell in cells]
                data_rows.append(row_data)

            if data_rows:
                header = data_rows[0]
                data = data_rows[1:]

    if header and data:
        print(f"\n  Extracted Header: {header}")
        print(f"  Extracted Data rows: {len(data)}")
        print(f"\n  Data preview:")
        for i, row in enumerate(data[:3], 1):
            print(f"    {i}. {row}")

        # 5. Test Cartesian Product generation
        print(f"\n🔄 Step 5: Testing Cartesian Product Generation...")

        definitions = []
        for row in data:
            # Split by slash for each cell
            options = []
            for cell in row:
                # Handle newline + slash
                cell_clean = cell.replace('\n', '').strip()
                values = [v.strip() for v in cell_clean.split('/') if v.strip()]
                options.append(values)

            # Generate combinations for this row
            from itertools import product
            for combo in product(*options):
                definition = {}
                for i, col_name in enumerate(header):
                    # Map column names
                    if i == 0 or "명칭" in col_name:
                        definition["보종명"] = combo[i]
                    else:
                        # Extract number from column name if exists
                        import re
                        match = re.search(r'(\d+)', col_name)
                        if match:
                            definition[f"유형{match.group(1)}"] = combo[i]
                        else:
                            definition[f"유형{i}"] = combo[i]
                definitions.append(definition)

        print(f"  ✅ Generated {len(definitions)} combinations")
        print(f"\n  First 5 combinations:")
        for i, defn in enumerate(definitions[:5], 1):
            print(f"    {i}. {json.dumps(defn, ensure_ascii=False)}")

        if len(definitions) > 5:
            print(f"    ... and {len(definitions) - 5} more")

        # 6. Summary
        print(f"\n" + "="*80)
        print("✅ EXTRACTION SUCCESS!")
        print("="*80)
        print(f"  📍 Section: [{target_section.index}] {target_section.title}")
        print(f"  📊 Header: {header}")
        print(f"  📈 Data rows: {len(data)}")
        print(f"  🎯 Total combinations: {len(definitions)}")
        print("="*80)

        # Save result
        result = {
            "success": True,
            "source_section": {
                "index": target_section.index,
                "title": target_section.title
            },
            "header": header,
            "data": data,
            "definitions": definitions,
            "total_count": len(definitions)
        }

        output_path = Path(doc_path).parent / f"{Path(doc_path).stem}_extracted.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n💾 Result saved to: {output_path.name}")
    else:
        print("  ⚠️  Could not extract header and data")


if __name__ == "__main__":
    main()
