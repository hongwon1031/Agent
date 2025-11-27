import copy
import json

from generate_test_variants import load_base, save_variant, TEST_DIR  # 재사용


def make_variant10_two_documents(base_docs):
    """동일 구조 문서를 두 개 담아서 multi-doc 입력을 테스트."""
    doc1 = copy.deepcopy(base_docs[0])
    doc1["doc_title"] += " / variant10_doc1"

    doc2 = copy.deepcopy(base_docs[0])
    doc2["doc_title"] += " / variant10_doc2"
    if doc2.get("elements"):
        doc2["elements"][0]["title"] = "1. (복제) " + doc2["elements"][0].get("title", "")

    return [doc1, doc2]


def make_variant11_missing_definition(base_docs):
    """정의 섹션(첫 번째 elements)을 제거하여 definition 없이 조건만 있는 문서."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant11_missing_definition"
    if doc.get("elements"):
        doc["elements"] = doc["elements"][1:]
    return [doc]


def make_variant12_condition_tables_swapped(base_docs):
    """조건 섹션 안에서 두 조건 표의 순서를 바꿈 (소제목은 그대로)."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant12_condition_tables_swapped"
    elements = doc.get("elements", [])
    if len(elements) >= 3:
        cond_el = elements[2]
        paras = cond_el.get("paragraphs", [])
        # 기대 구조: [title, table, table, title, table, text]
        if len(paras) >= 5 and paras[1].get("type") == "table" and paras[4].get("type") == "table":
            swapped = paras[:]
            swapped[1], swapped[4] = swapped[4], swapped[1]
            cond_el["paragraphs"] = swapped
    return [doc]


def make_variant13_condition_text_only(base_docs):
    """조건 섹션의 표를 모두 제거하고 텍스트만 남김."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant13_condition_text_only"
    elements = doc.get("elements", [])
    if len(elements) >= 3:
        cond_el = elements[2]
        new_paras = []
        for p in cond_el.get("paragraphs", []):
            if p.get("type") == "table":
                new_paras.append(
                    {
                        "type": "text",
                        "content": p.get("content", ""),
                        "table": {"table_title": "", "table_elements": []},
                    }
                )
            else:
                new_paras.append(p)
        cond_el["paragraphs"] = new_paras
    return [doc]


def make_variant14_noisy_sections(base_docs):
    """임의의 노이즈 섹션(불필요한 안내문)을 앞/뒤에 추가."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant14_noisy_sections"
    noise_prefix = {
        "title": "※ 안내문: 이 섹션은 가입조건과 무관합니다",
        "paragraphs": [
            {
                "type": "text",
                "content": "이 문단은 테스트를 위한 노이즈입니다. Planner가 무시해야 합니다.",
                "table": {"table_title": "", "table_elements": []},
            }
        ],
    }
    noise_suffix = {
        "title": "부록. 용어 설명(테스트용)",
        "paragraphs": [
            {
                "type": "text",
                "content": "여기도 가입조건과 직접적 관련은 없는 설명 텍스트입니다.",
                "table": {"table_title": "", "table_elements": []},
            }
        ],
    }
    doc["elements"] = [noise_prefix] + doc["elements"] + [noise_suffix]
    return [doc]


def make_variant15_multi_condition_sections(base_docs):
    """조건 섹션을 하나 더 복제하여 두 개의 조건 섹션이 있는 문서."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant15_multi_condition_sections"
    elements = doc.get("elements", [])
    if len(elements) >= 3:
        cond_el = copy.deepcopy(elements[2])
        cond_el["title"] = "3-1. (추가) " + cond_el.get("title", "")
        elements.insert(3, cond_el)
        doc["elements"] = elements
    return [doc]


def make_variant16_definition_in_middle(base_docs):
    """정의 섹션을 문서 중간(예: index 3)으로 이동."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant16_definition_in_middle"
    elements = doc.get("elements", [])
    if elements:
        def_el = elements.pop(0)
        insert_idx = min(3, len(elements))
        elements.insert(insert_idx, def_el)
        doc["elements"] = elements
    return [doc]


def make_variant17_flatten_tables_to_text(base_docs):
    """모든 table paragraph를 text로 바꾸고 table_elements는 비워서 '텍스트 기반' 파서 테스트."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant17_flatten_tables_to_text"
    for el in doc.get("elements", []):
        new_paras = []
        for p in el.get("paragraphs", []):
            if p.get("type") == "table":
                new_paras.append(
                    {
                        "type": "text",
                        "content": p.get("content", ""),
                        "table": {"table_title": "", "table_elements": []},
                    }
                )
            else:
                new_paras.append(p)
        el["paragraphs"] = new_paras
    return [doc]


def make_variant18_missing_titles(base_docs):
    """모든 섹션 title을 빈 문자열로 만들어, title 없이 구조를 파악해야 하는 케이스."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant18_missing_titles"
    for el in doc.get("elements", []):
        el["title"] = ""
    return [doc]


def make_variant19_split_definition(base_docs):
    """정의 표를 새 섹션으로 분리: 첫 섹션은 텍스트만, 두 번째 섹션은 표만."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant19_split_definition"
    elements = doc.get("elements", [])
    if not elements:
        return [doc]
    def_el = elements[0]
    paras = def_el.get("paragraphs", [])
    text_paras = []
    table_paras = []
    for p in paras:
        if p.get("type") == "table":
            table_paras.append(p)
        else:
            text_paras.append(p)
    if table_paras:
        from copy import deepcopy

        def_el_text = deepcopy(def_el)
        def_el_text["paragraphs"] = text_paras or []
        def_el_text["title"] = "1. 보험종목의 명칭(텍스트 부분)"

        def_el_table = deepcopy(def_el)
        def_el_table["paragraphs"] = table_paras
        def_el_table["title"] = "1-1. 보험종목의 명칭(표 부분)"

        elements[0] = def_el_text
        elements.insert(1, def_el_table)
        doc["elements"] = elements
    return [doc]


def make_variant20_english_doc(base_docs):
    """영어로 작성된 정의/조건 문서."""
    doc = {
        "doc_title": "Sample Accident Disability Rider (English Variant)",
        "elements": [
            {
                "title": "1. Product Name and Type",
                "paragraphs": [
                    {
                        "type": "table",
                        "content": "<table>...</table>",
                        "table": {
                            "table_title": "Product Definition",
                            "table_elements": [
                                {
                                    "Product Name": "Accident Disability Rider (Non-Refund)",
                                    "Plan Type": "Non-Refund",
                                    "Underwriting Type": "Simplified (315) / Simplified (335) / Standard",
                                },
                                {
                                    "Product Name": "Accident Disability Rider",
                                    "Plan Type": "Standard",
                                    "Underwriting Type": "Standard",
                                },
                            ],
                        },
                    }
                ],
            },
            {
                "title": "3. Coverage Period and Premium Payment",
                "paragraphs": [
                    {
                        "type": "table",
                        "content": "<table>...</table>",
                        "table": {
                            "table_title": "Eligibility",
                            "table_elements": [
                                {
                                    "Plan Type": "Non-Refund",
                                    "Coverage Period": "20 / 30 years, Whole Life",
                                    "Payment Period": "10 / 20 years",
                                    "Male Age": "15 - 65",
                                    "Female Age": "15 - 65",
                                },
                                {
                                    "Plan Type": "Standard",
                                    "Coverage Period": "20 / 30 years",
                                    "Payment Period": "10 / 20 years",
                                    "Male Age": "15 - 60",
                                    "Female Age": "15 - 60",
                                },
                            ],
                        },
                    }
                ],
            },
        ],
    }
    return [doc]


def make_variant21_chinese_doc(base_docs):
    """한자/중국어 느낌의 문서."""
    doc = {
        "doc_title": "簡易癌症診斷附約（非分紅，解約金不給付）",
        "elements": [
            {
                "title": "一、保險種類名稱",
                "paragraphs": [
                    {
                        "type": "table",
                        "content": "<table>...</table>",
                        "table": {
                            "table_title": "保險種類說明",
                            "table_elements": [
                                {
                                    "名稱": "簡易癌症診斷附約（非分紅，解約金不給付）",
                                    "保險種類": "解約金不給付型",
                                    "審核型態": "簡易核保型 / 一般核保型",
                                },
                                {
                                    "名稱": "簡易癌症診斷附約（非分紅）",
                                    "保險種類": "一般型",
                                    "審核型態": "一般核保型",
                                },
                            ],
                        },
                    }
                ],
            },
            {
                "title": "三、保險期間及保費繳納期間",
                "paragraphs": [
                    {
                        "type": "table",
                        "content": "<table>...</table>",
                        "table": {
                            "table_title": "投保資格",
                            "table_elements": [
                                {
                                    "保險種類": "解約金不給付型",
                                    "保險期間": "20年 / 30年 / 終身",
                                    "繳納期間": "10年 / 20年",
                                    "投保年齡": "15歲至65歲",
                                },
                                {
                                    "保險種類": "一般型",
                                    "保險期間": "20年 / 30年",
                                    "繳納期間": "10年 / 20年",
                                    "投保年齡": "15歲至60歲",
                                },
                            ],
                        },
                    }
                ],
            },
        ],
    }
    return [doc]


def make_variant22_many_typos(base_docs):
    """오타가 많이 섞인 문서 (컬럼/제목/텍스트에 오타)."""
    doc = copy.deepcopy(base_docs[0])
    doc["doc_title"] += " / variant22_many_typos"

    # 정의 섹션 제목 오타
    if doc.get("elements"):
        el0 = doc["elements"][0]
        el0["title"] = "1. 보헙종목의 멍칭"  # 보험종목의 명칭 오타
        for p in el0.get("paragraphs", []):
            if p.get("type") == "table":
                tbl = p.get("table", {})
                new_rows = []
                for row in tbl.get("table_elements", []):
                    new_row = {}
                    for k, v in row.items():
                        kk = k.replace("��Ī", "멍칭").replace("��������", "보헙좀목")
                        vv = v.replace("해약환급금", "해약환급굼")
                        new_row[kk] = vv
                    new_rows.append(new_row)
                tbl["table_elements"] = new_rows

    # 조건 섹션 텍스트/컬럼 오타
    for el in doc.get("elements", []):
        title = el.get("title", "")
        if "����Ⱓ" in title and "���Գ���" in title:
            paras = el.get("paragraphs", [])
            for p in paras:
                if p.get("type") == "table":
                    tbl = p.get("table", {})
                    new_rows = []
                    for row in tbl.get("table_elements", []):
                        new_row = {}
                        for k, v in row.items():
                            kk = (
                                k.replace("����Ⱓ", "보헙기간")
                                .replace("����� ���ԱⰣ", "납입기갼")
                                .replace("���ڳ���", "남자나이")
                            )
                            vv = v.replace("년납", "넌납").replace("만기", "망기")
                            new_row[kk] = vv
                        new_rows.append(new_row)
                    tbl["table_elements"] = new_rows
    return [doc]


def main():
    base_docs = load_base()

    variants = {
        "test_variant10_two_documents.json": make_variant10_two_documents(base_docs),
        "test_variant11_missing_definition.json": make_variant11_missing_definition(base_docs),
        "test_variant12_condition_tables_swapped.json": make_variant12_condition_tables_swapped(base_docs),
        "test_variant13_condition_text_only.json": make_variant13_condition_text_only(base_docs),
        "test_variant14_noisy_sections.json": make_variant14_noisy_sections(base_docs),
        "test_variant15_multi_condition_sections.json": make_variant15_multi_condition_sections(base_docs),
        "test_variant16_definition_in_middle.json": make_variant16_definition_in_middle(base_docs),
        "test_variant17_flatten_tables_to_text.json": make_variant17_flatten_tables_to_text(base_docs),
        "test_variant18_missing_titles.json": make_variant18_missing_titles(base_docs),
        "test_variant19_split_definition.json": make_variant19_split_definition(base_docs),
        "test_variant20_english_doc.json": make_variant20_english_doc(base_docs),
        "test_variant21_chinese_doc.json": make_variant21_chinese_doc(base_docs),
        "test_variant22_many_typos.json": make_variant22_many_typos(base_docs),
    }

    for name, docs in variants.items():
        save_variant(name, docs)


if __name__ == "__main__":
    main()
