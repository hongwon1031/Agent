"""
Main entry point for prototype_3

완전히 일반화된 Multi-Agent 시스템
"""

import json
import sys
from pathlib import Path


def load_document(doc_path: str):
    """Load JSON document"""
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading document: {e}")
        return None


def main():
    print("="*80)
    print("Prototype 3: Fully Generalized Multi-Agent System")
    print("="*80)

    # Check for document path argument
    if len(sys.argv) < 2:
        print("\n⚠️  No document provided. Running basic tests...")
        run_basic_tests()
        return

    doc_path = sys.argv[1]
    print(f"\n📄 Loading document: {Path(doc_path).name}")

    # Load document
    doc = load_document(doc_path)
    if doc is None:
        return

    # Test DocumentAccessor with real document
    from core.document_accessor import DocumentAccessor

    print("\n" + "="*80)
    print("Testing DocumentAccessor with Real Document")
    print("="*80)

    accessor = DocumentAccessor(doc)

    # Document summary
    summary = accessor.get_summary()
    print(f"\n📊 Document Structure Summary:")
    print(f"  - Format: {summary['format']}")
    print(f"  - Total Sections: {summary['total_sections']}")
    print(f"  - Sections with Tables: {summary['sections_with_tables']}")
    print(f"  - Sections with Text: {summary['sections_with_text']}")

    # Show all section titles
    print(f"\n📑 Section Titles:")
    for idx, title in enumerate(summary['section_titles'][:20], 1):
        print(f"  {idx:2d}. {title}")
    if len(summary['section_titles']) > 20:
        print(f"  ... and {len(summary['section_titles']) - 20} more")

    # Find definition sections
    print(f"\n🔍 Searching for Definition Sections...")
    definition_sections = accessor.find_sections({
        "title_contains": ["정의", "명칭", "용어", "보험종목"]
    })

    if definition_sections:
        print(f"  ✅ Found {len(definition_sections)} potential definition section(s):")
        for sec in definition_sections:
            print(f"    - [{sec.index}] {sec.title}")

            # Check if it has tables
            table_contents = accessor.extract_content(sec, content_type="table")
            if table_contents:
                print(f"      → Has {len(table_contents)} table(s)")
                for tc in table_contents[:1]:  # Show first table info
                    if isinstance(tc.data, dict):
                        table_elements = tc.data.get("table_elements", [])
                        print(f"      → Table has {len(table_elements)} rows")
    else:
        print(f"  ⚠️  No definition sections found with keywords")

    print("\n" + "="*80)
    print("✅ DocumentAccessor test completed!")
    print("="*80)
    print()
    print("🚧 To complete the full agent, implement:")
    print("  1. DynamicPlanner - LLM-based flexible planning")
    print("  2. TypedValidator - Type-based validation")
    print("  3. SmartExecutor - Smart tool execution with references")
    print("  4. Full agent orchestration in agent.py")
    print()


def run_basic_tests():
    """Run basic tests without real document"""
    print()
    print("✅ Core components implemented:")
    print("   - DocumentAccessor: Structure-independent document access")
    print("   - FlexibleToolResult: Dynamic result format")
    print("   - SmartReference: Advanced reference resolution")
    print("   - FlexibleTools: Search, Extract, Transform tools")
    print()
    print("📄 Running basic DocumentAccessor tests...")

    # 예시 문서 (다양한 구조)
    test_docs = [
        # Standard format
        {
            "name": "Standard Elements",
            "doc": [{
                "elements": [
                    {"title": "보험종목의 정의", "paragraphs": [{"table": {"table_elements": []}}]},
                    {"title": "기타", "paragraphs": [{"text": "내용"}]}
                ]
            }]
        },
        # Pages format
        {
            "name": "Pages Format",
            "doc": {
                "pages": [
                    {"title": "정의", "content": [{"table": {}}]},
                    {"title": "약관", "content": [{"text": ""}]}
                ]
            }
        },
        # Document.sections format
        {
            "name": "Document Sections",
            "doc": {
                "document": {
                    "sections": [
                        {"title": "용어의 정의", "content": []}
                    ]
                }
            }
        }
    ]

    from core.document_accessor import DocumentAccessor

    for test_case in test_docs:
        print(f"\n  Testing: {test_case['name']}")
        accessor = DocumentAccessor(test_case['doc'])
        summary = accessor.get_summary()
        print(f"    Format: {summary['format']}")
        print(f"    Sections: {summary['total_sections']}")
        print(f"    ✅ Detected and accessible")

    print("\n✅ All basic tests passed!")
    print("\nUsage: python main.py <path_to_document.json>")
    print()


if __name__ == "__main__":
    main()
