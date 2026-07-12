from __future__ import annotations

import io
import math
import re
import zipfile
from datetime import date, datetime
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape


_INVALID_SHEET_NAME_RE = re.compile(r"[\\[\\]:*?/\\\\]")
_MAX_SHEET_NAME_LENGTH = 31


def _column_name(index: int) -> str:
    """Return the Excel column label for a one-based column index."""
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _sheet_name(value: object, used: set[str], fallback_index: int) -> str:
    base = _INVALID_SHEET_NAME_RE.sub("_", str(value or "").strip()).strip("'")
    base = (base or f"Sheet{fallback_index}")[:_MAX_SHEET_NAME_LENGTH]
    candidate = base
    suffix = 2
    while candidate.lower() in used:
        marker = f"_{suffix}"
        candidate = f"{base[: _MAX_SHEET_NAME_LENGTH - len(marker)]}{marker}"
        suffix += 1
    used.add(candidate.lower())
    return candidate


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return str(value).replace("\x00", "")


def _xml_attribute(value: Any) -> str:
    return escape(_text(value), entities={'"': "&quot;"})


def _inline_string_cell(reference: str, value: Any, style: int | None = None) -> str:
    text = escape(_text(value))
    attrs = f' r="{reference}" t="inlineStr"'
    if style is not None:
        attrs += f' s="{style}"'
    preserve = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") or "\n" in text else ""
    return f"<c{attrs}><is><t{preserve}>{text}</t></is></c>"


def _sheet_xml(headers: Sequence[object], rows: Iterable[Sequence[Any]]) -> str:
    rendered_rows: list[str] = []
    column_widths = [len(_text(header)) for header in headers]

    def append_row(row_index: int, values: Sequence[Any], *, header: bool = False) -> None:
        cells: list[str] = []
        for column_index, value in enumerate(values, start=1):
            if column_index > len(column_widths):
                column_widths.append(0)
            text = _text(value)
            column_widths[column_index - 1] = min(48, max(column_widths[column_index - 1], len(text)))
            cells.append(_inline_string_cell(f"{_column_name(column_index)}{row_index}", text, 1 if header else None))
        rendered_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    append_row(1, headers, header=True)
    for row_index, row in enumerate(rows, start=2):
        append_row(row_index, row)

    columns = "".join(
        f'<col min="{index}" max="{index}" width="{max(10, min(52, width + 2))}" customWidth="1"/>'
        for index, width in enumerate(column_widths, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<cols>{columns}</cols><sheetData>{''.join(rendered_rows)}</sheetData>"
        "<autoFilter ref=\"A1:"
        f"{_column_name(max(1, len(headers)))}1\"/>"
        "</worksheet>"
    )


def build_xlsx_workbook(sheets: Iterable[tuple[object, Sequence[object], Iterable[Sequence[Any]]]]) -> bytes:
    """Build a minimal, dependency-free XLSX workbook with string cells.

    The exporter only needs portable tabular output, so inline strings avoid a
    shared-string table and keep the implementation small. Excel, LibreOffice,
    and Numbers all open this Open XML subset.
    """
    normalized: list[tuple[str, Sequence[object], Iterable[Sequence[Any]]]] = []
    used_names: set[str] = set()
    for index, (name, headers, rows) in enumerate(sheets, start=1):
        normalized.append((_sheet_name(name, used_names, index), list(headers), rows))
    if not normalized:
        normalized.append(("Sheet1", [], []))

    workbook_sheets = "".join(
        f'<sheet name="{_xml_attribute(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _headers, _rows) in enumerate(normalized, start=1)
    )
    workbook_rels = "".join(
        '<Relationship '
        f'Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(normalized) + 1)
    )
    workbook_rels += (
        f'<Relationship Id="rId{len(normalized) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    content_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(normalized) + 1)
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f"{content_overrides}"
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{workbook_rels}</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="2"><xf xfId="0"/><xf xfId="0" applyFont="1" fontId="1"/></cellXfs>'
            '</styleSheet>',
        )
        for index, (_name, headers, rows) in enumerate(normalized, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(headers, rows))
    return output.getvalue()
