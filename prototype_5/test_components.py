"""
DocumentAccessor와 DocumentAnalyzer 비교 테스트
"""

import json
import sys
from pathlib import Path
from core.document_accessor import DocumentAccessor
from core.llm_document_analyzer import LLMDocumentAnalyzer


def load_document(doc_path: str):
    """Load JSON document"""
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading document: {e}")
        return None


def test_document_accessor(doc):
    """DocumentAccessor 테스트"""
    print("\n" + "="*80)
    print("1. DocumentAccessor (Rule-based, Fast)")
    print("="*80)

    accessor = DocumentAccessor(doc)

    # 모든 섹션 추출
    sections = accessor.get_all_sections()

    print(f"\n[결과] 추출된 섹션 수: {len(sections)}")
    print(f"\n섹션 상세:")
    for i, section in enumerate(sections):
        print(f"\n  Section {i}:")
        print(f"    - Title: {section.title}")
        print(f"    - Content Items: {len(section.content_items)}개")

        if section.content_summary:
            summary = section.content_summary
            print(f"    - Has Table: {summary.get('has_table')}")
            print(f"    - Has Text: {summary.get('has_text')}")
            print(f"    - Primary Type: {summary.get('primary_type')}")
            print(f"    - Table Count: {summary.get('table_count')}")
            print(f"    - Text Count: {summary.get('text_count')}")

            preview = summary.get('content_preview', '')
            if preview:
                preview_short = preview[:100] + "..." if len(preview) > 100 else preview
                print(f"    - Content Preview: {preview_short}")

    # 전체 요약
    doc_summary = accessor.get_summary()
    print(f"\n[문서 전체 요약]")
    print(f"  - Format: {doc_summary.get('format')}")
    print(f"  - Total Sections: {doc_summary.get('total_sections')}")
    print(f"  - Sections with Tables: {doc_summary.get('sections_with_tables')}")
    print(f"  - Sections with Text: {doc_summary.get('sections_with_text')}")

    sections_by_format = doc_summary.get('sections_by_format', {})
    print(f"\n  - Sections by Format:")
    print(f"    • Table Only: {sections_by_format.get('table_only', [])}")
    print(f"    • Text Only: {sections_by_format.get('text_only', [])}")
    print(f"    • Mixed: {sections_by_format.get('mixed', [])}")
    print(f"    • Unknown: {sections_by_format.get('unknown', [])}")

    return doc_summary


def test_llm_analyzer(doc):
    """LLM DocumentAnalyzer 테스트"""
    print("\n" + "="*80)
    print("2. LLM DocumentAnalyzer (AI-based, Intelligent)")
    print("="*80)

    analyzer = LLMDocumentAnalyzer()

    print("\n[LLM에게 문서 분석 요청 중...]")
    analysis = analyzer.analyze(doc)

    print(f"\n[결과]")
    print(f"  - Structure Type: {analysis.get('structure_type')}")
    print(f"  - Sections Path: {analysis.get('sections_path')}")
    print(f"  - Title Field: {analysis.get('title_field')}")
    print(f"  - Content Field: {analysis.get('content_field')}")
    print(f"  - Table Patterns: {analysis.get('table_patterns')}")
    print(f"  - Total Sections Estimate: {analysis.get('total_sections_estimate')}")
    print(f"  - Confidence: {analysis.get('confidence')}")

    reasoning = analysis.get('reasoning', '')
    if reasoning:
        print(f"\n[LLM의 분석 설명]")
        print(f"  {reasoning}")

    # Sample Section 출력
    sample_section = analysis.get('sample_section')
    if sample_section:
        print(f"\n[Sample Section]")
        print(f"  {json.dumps(sample_section, ensure_ascii=False, indent=2)[:500]}...")

    return analysis


def compare_results(accessor_summary, llm_analysis):
    """두 결과 비교"""
    print("\n" + "="*80)
    print("3. 비교 결과")
    print("="*80)

    print("\n[섹션 수 비교]")
    print(f"  DocumentAccessor: {accessor_summary.get('total_sections')}개")
    print(f"  LLM Analyzer: {llm_analysis.get('total_sections_estimate')}개")

    if accessor_summary.get('total_sections') == llm_analysis.get('total_sections_estimate'):
        print("  ✅ 일치!")
    else:
        print("  ⚠️ 불일치")

    print("\n[처리 속도]")
    print("  DocumentAccessor: ~0.1초 (매우 빠름)")
    print("  LLM Analyzer: ~2-5초 (LLM 호출)")

    print("\n[제공 정보]")
    print("  DocumentAccessor:")
    print("    - Section 객체 리스트 (실제 데이터)")
    print("    - 각 섹션의 content_summary (table/text/mixed)")
    print("    - sections_by_format (형식별 분류)")

    print("  LLM Analyzer:")
    print("    - structure_type (문서 구조 유형)")
    print("    - sections_path (섹션 접근 경로)")
    print("    - reasoning (LLM의 판단 근거)")
    print("    - confidence (신뢰도)")

    print("\n[사용 목적]")
    print("  DocumentAccessor: 실제 섹션 추출 + 형식 메타데이터")
    print("  LLM Analyzer: 문서 구조 이해 + 경로 찾기")


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_components.py <document_path>")
        print("\nExample:")
        print('  python test_components.py "data/토이프로젝트_데이터/test/test.json"')
        sys.exit(1)

    doc_path = sys.argv[1]
    print(f"\n📄 Input document: {Path(doc_path).name}")

    # 문서 로드
    doc = load_document(doc_path)
    if doc is None:
        sys.exit(1)

    # 1. DocumentAccessor 테스트
    accessor_summary = test_document_accessor(doc)

    # 2. LLM DocumentAnalyzer 테스트
    llm_analysis = test_llm_analyzer(doc)

    # 3. 비교
    compare_results(accessor_summary, llm_analysis)

    print("\n" + "="*80)
    print("테스트 완료!")
    print("="*80)


if __name__ == "__main__":
    main()
