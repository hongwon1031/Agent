import argparse
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


_CELL_REF_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _normalize_xlsx_target_path(target: str) -> str:
    normalized = (target or "").strip().replace("\\", "/")
    normalized = normalized.rstrip("/")
    normalized = normalized.lstrip("/")
    if normalized.startswith("xl/"):
        return normalized
    return f"xl/{normalized}"


def _col_letters_to_index(letters: str) -> int:
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def _infer_type(value: str) -> Any:
    if value is None:
        return None

    s = value.strip()
    if s == "":
        return ""

    if s in ("TRUE", "True", "true"):
        return True
    if s in ("FALSE", "False", "false"):
        return False

    try:
        if re.fullmatch(r"[+-]?[0-9]+", s):
            return int(s)
        if re.fullmatch(r"[+-]?([0-9]*\\.[0-9]+|[0-9]+\\.[0-9]*)([eE][+-]?[0-9]+)?", s) or re.fullmatch(
            r"[+-]?[0-9]+([eE][+-]?[0-9]+)", s
        ):
            return float(s)
    except ValueError:
        return s

    return s


def _read_xml(z: zipfile.ZipFile, name: str) -> Optional[ET.Element]:
    try:
        data = z.read(name)
    except KeyError:
        return None
    return ET.fromstring(data)


def _parse_shared_strings(z: zipfile.ZipFile) -> List[str]:
    root = _read_xml(z, "xl/sharedStrings.xml")
    if root is None:
        return []

    strings: List[str] = []
    for si in root.findall(".//{*}si"):
        texts = [t.text or "" for t in si.findall(".//{*}t")]
        strings.append("".join(texts))
    return strings


def _parse_workbook_sheets(z: zipfile.ZipFile) -> List[Tuple[str, str]]:
    workbook = _read_xml(z, "xl/workbook.xml")
    rels = _read_xml(z, "xl/_rels/workbook.xml.rels")
    if workbook is None or rels is None:
        raise ValueError("Invalid xlsx: missing workbook metadata")

    rid_to_target: Dict[str, str] = {}
    for rel in rels.findall(".//{*}Relationship"):
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rid and target:
            rid_to_target[rid] = target

    sheets: List[Tuple[str, str]] = []
    for sheet in workbook.findall(".//{*}sheets/{*}sheet"):
        name = sheet.attrib.get("name") or ""
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        if not rid:
            continue
        target = rid_to_target.get(rid)
        if not target:
            continue
        path = _normalize_xlsx_target_path(target)
        sheets.append((name, path))

    return sheets


def _parse_sheet_rows(
    z: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: List[str],
    infer_types: bool,
) -> List[List[Any]]:
    root = _read_xml(z, sheet_path)
    if root is None:
        raise ValueError(f"Sheet not found: {sheet_path}")

    cells_by_row: Dict[int, Dict[int, Any]] = {}
    max_col = -1

    for row in root.findall(".//{*}sheetData/{*}row"):
        for cell in row.findall("{*}c"):
            ref = cell.attrib.get("r")
            if not ref:
                continue

            match = _CELL_REF_RE.match(ref)
            if not match:
                continue

            col_letters, row_digits = match.groups()
            row_index = int(row_digits) - 1
            col_index = _col_letters_to_index(col_letters)
            max_col = max(max_col, col_index)

            cell_type = cell.attrib.get("t")
            value_elem = cell.find("{*}v")
            inline_elem = cell.find("{*}is")

            value: Any = None
            if cell_type == "s" and value_elem is not None and value_elem.text is not None:
                try:
                    value = shared_strings[int(value_elem.text)]
                except (ValueError, IndexError):
                    value = value_elem.text
            elif cell_type == "inlineStr" and inline_elem is not None:
                texts = [t.text or "" for t in inline_elem.findall(".//{*}t")]
                value = "".join(texts)
            elif value_elem is not None:
                value = value_elem.text

            if infer_types and isinstance(value, str):
                value = _infer_type(value)

            if row_index not in cells_by_row:
                cells_by_row[row_index] = {}
            cells_by_row[row_index][col_index] = value

    if max_col < 0:
        return []

    rows: List[List[Any]] = []
    for row_index in sorted(cells_by_row.keys()):
        row_list = [None] * (max_col + 1)
        for col_index, value in cells_by_row[row_index].items():
            if 0 <= col_index <= max_col:
                row_list[col_index] = value
        rows.append(row_list)

    return rows


def _is_empty_cell(value: Any) -> bool:
    return value is None or value == ""


def _find_header_row_index(rows: List[List[Any]]) -> Optional[int]:
    for i, row in enumerate(rows):
        if any(not _is_empty_cell(v) for v in row):
            return i
    return None


def _make_unique_headers(headers: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    unique: List[str] = []
    for h in headers:
        key = h if h else "column"
        count = seen.get(key, 0) + 1
        seen[key] = count
        unique.append(key if count == 1 else f"{key}_{count}")
    return unique


def _rows_to_records(
    rows: List[List[Any]],
    header_row: Optional[int],
    keep_nulls: bool,
) -> List[Dict[str, Any]]:
    if not rows:
        return []

    header_index = header_row if header_row is not None else _find_header_row_index(rows)
    if header_index is None:
        return []

    raw_headers = ["" if v is None else str(v).strip() for v in rows[header_index]]
    headers = _make_unique_headers(raw_headers)

    records: List[Dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if not any(not _is_empty_cell(v) for v in row):
            continue

        record: Dict[str, Any] = {}
        for idx, key in enumerate(headers):
            value = row[idx] if idx < len(row) else None
            if keep_nulls or not _is_empty_cell(value):
                record[key] = value
        records.append(record)

    return records


@dataclass(frozen=True)
class ConvertResult:
    sheet_name: str
    output: Any


def convert_xlsx(
    input_path: Path,
    sheet: Optional[str],
    all_sheets: bool,
    mode: str,
    header_row: Optional[int],
    keep_nulls: bool,
    infer_types: bool,
) -> List[ConvertResult]:
    with zipfile.ZipFile(input_path) as z:
        shared_strings = _parse_shared_strings(z)
        sheets = _parse_workbook_sheets(z)

        if not sheets:
            raise ValueError("No worksheets found")

        selected: List[Tuple[str, str]] = []
        if all_sheets:
            selected = sheets
        elif sheet is None:
            selected = [sheets[0]]
        else:
            by_name = {name: path for name, path in sheets}
            if sheet in by_name:
                selected = [(sheet, by_name[sheet])]
            else:
                try:
                    index = int(sheet)
                    selected = [sheets[index]]
                except (ValueError, IndexError):
                    raise ValueError(f"Sheet not found: {sheet}")

        results: List[ConvertResult] = []
        for sheet_name, sheet_path in selected:
            rows = _parse_sheet_rows(z, sheet_path, shared_strings, infer_types=infer_types)
            if mode == "records":
                output = _rows_to_records(rows, header_row=header_row, keep_nulls=keep_nulls)
            elif mode == "rows":
                output = rows
            else:
                raise ValueError(f"Unsupported mode: {mode}")
            results.append(ConvertResult(sheet_name=sheet_name, output=output))

        return results


def list_sheets(input_path: Path) -> List[str]:
    with zipfile.ZipFile(input_path) as z:
        return [name for name, _ in _parse_workbook_sheets(z)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert .xlsx to JSON without external dependencies.")
    parser.add_argument("input", type=str, help="Path to .xlsx file")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output json path")
    parser.add_argument("--mode", choices=["records", "rows"], default="records")
    parser.add_argument("--sheet", type=str, default=None, help="Sheet name or 0-based index")
    parser.add_argument("--all-sheets", action="store_true", help="Export all sheets")
    parser.add_argument("--header-row", type=int, default=None, help="0-based header row index")
    parser.add_argument("--keep-nulls", action="store_true", help="Keep null/empty cells as keys in records")
    parser.add_argument("--no-infer-types", action="store_true", help="Keep all cell values as strings")
    parser.add_argument("--list-sheets", action="store_true", help="List sheet names and exit")

    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"File not found: {input_path}")

    if args.list_sheets:
        for name in list_sheets(input_path):
            print(name)
        return 0

    results = convert_xlsx(
        input_path=input_path,
        sheet=args.sheet,
        all_sheets=args.all_sheets,
        mode=args.mode,
        header_row=args.header_row,
        keep_nulls=bool(args.keep_nulls),
        infer_types=not bool(args.no_infer_types),
    )

    output_path = Path(args.output) if args.output else input_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.all_sheets:
        payload = {r.sheet_name: r.output for r in results}
    else:
        payload = results[0].output if results else []

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
