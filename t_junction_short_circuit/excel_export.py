"""Plain Excel export for scenario-aware short-circuit result tables.

The workbook deliberately uses default-looking fonts and colours. It applies
only centered cells, bold titles/headers, borders, and the final three-decimal
number format needed for an engineering calculation deliverable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from .calculator import CalculationResult
from .presentation import (
    HIGH_VOLTAGE_RESULT_TABLE_HEADERS,
    LOW_VOLTAGE_RESULT_TABLE_HEADERS,
)

MAIN_TITLE = "短路电流计算"
HIGH_HEADERS = HIGH_VOLTAGE_RESULT_TABLE_HEADERS
LOW_HEADERS = LOW_VOLTAGE_RESULT_TABLE_HEADERS

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

ET.register_namespace("", _MAIN_NS)
ET.register_namespace("r", _DOC_REL_NS)


def _q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def _column_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_ref(row: int, column: int) -> str:
    return f"{_column_letter(column)}{row}"


def _format_voltage(value: float) -> str:
    return f"{value:g} kV"


def _table_titles(result: CalculationResult) -> tuple[str, str]:
    high = _format_voltage(result.system_source_station_high.voltage_kv)
    if result.t_opposite_station_high is None:
        first = f"表 1  系统电源侧变电站{high}侧系统总短路电流（kA）"
    else:
        first = f"表 1  T 接两侧变电站{high}侧系统总短路电流（kA）"
    return first, f"表 2  {result.pv_station_name}系统总短路电流（kA）"


def result_table_rows(
    result: CalculationResult,
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """Return raw numeric rows for Table 1 and Table 2's high/low blocks."""

    station_rows: list[tuple[Any, ...]] = [
        (
            result.system_source_station_high.label,
            result.system_source_station_high.three_phase_total_ka,
            result.system_source_station_high.single_phase_total_ka,
            result.system_source_station_high.two_phase_ground_total_ka,
        )
    ]
    if result.t_opposite_station_high is not None:
        item = result.t_opposite_station_high
        station_rows.append(
            (item.label, item.three_phase_total_ka, item.single_phase_total_ka, item.two_phase_ground_total_ka)
        )
    high = result.pv_station_high
    low = result.pv_station_low
    return (
        station_rows,
        [(high.label, high.three_phase_total_ka, high.single_phase_total_ka, high.two_phase_ground_total_ka)],
        [(low.label, low.three_phase_total_ka, low.two_phase_total_ka)],
    )


def _inline_string_cell(reference: str, value: str, style_id: int) -> ET.Element:
    cell = ET.Element(_q(_MAIN_NS, "c"), {"r": reference, "t": "str", "s": str(style_id)})
    ET.SubElement(cell, _q(_MAIN_NS, "v")).text = value
    return cell


def _number_cell(reference: str, value: float, style_id: int) -> ET.Element:
    cell = ET.Element(_q(_MAIN_NS, "c"), {"r": reference, "t": "n", "s": str(style_id)})
    ET.SubElement(cell, _q(_MAIN_NS, "v")).text = f"{value:.12g}"
    return cell


def _append_row(sheet_data: ET.Element, row_index: int, cells: list[ET.Element], *, height: float | None = None) -> None:
    attrs = {"r": str(row_index)}
    if height is not None:
        attrs.update({"ht": str(height), "customHeight": "1"})
    row = ET.SubElement(sheet_data, _q(_MAIN_NS, "row"), attrs)
    for cell in cells:
        row.append(cell)


def _append_heading(sheet_data: ET.Element, row_index: int, text: str) -> None:
    _append_row(sheet_data, row_index, [_inline_string_cell(_cell_ref(row_index, 1), text, 3)], height=21)


def _append_block(
    sheet_data: ET.Element,
    start_row: int,
    headers: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> int:
    _append_row(
        sheet_data,
        start_row,
        [_inline_string_cell(_cell_ref(start_row, column), header, 3) for column, header in enumerate(headers, start=1)],
        height=20,
    )
    for offset, values in enumerate(rows, start=1):
        row_index = start_row + offset
        cells: list[ET.Element] = []
        for column, value in enumerate(values, start=1):
            reference = _cell_ref(row_index, column)
            cells.append(_number_cell(reference, float(value), 2) if isinstance(value, (int, float)) else _inline_string_cell(reference, str(value), 1))
        _append_row(sheet_data, row_index, cells, height=19)
    return start_row + 1 + len(rows)


def _worksheet_xml(result: CalculationResult) -> bytes:
    station_rows, pv_high_rows, pv_low_rows = result_table_rows(result)
    table_1_title, table_2_title = _table_titles(result)
    high_label = result.pv_station_high.label
    low_label = result.pv_station_low.label

    worksheet = ET.Element(_q(_MAIN_NS, "worksheet"))
    ET.SubElement(worksheet, _q(_MAIN_NS, "sheetFormatPr"), {"defaultRowHeight": "15"})
    cols = ET.SubElement(worksheet, _q(_MAIN_NS, "cols"))
    ET.SubElement(cols, _q(_MAIN_NS, "col"), {"min": "1", "max": "1", "width": "34", "customWidth": "1"})
    ET.SubElement(cols, _q(_MAIN_NS, "col"), {"min": "2", "max": "4", "width": "20", "customWidth": "1"})
    sheet_data = ET.SubElement(worksheet, _q(_MAIN_NS, "sheetData"))

    _append_heading(sheet_data, 1, MAIN_TITLE)
    _append_row(sheet_data, 2, [_inline_string_cell("A2", "结果单位：kA；最终短路电流保留 3 位小数。", 1)], height=19)
    _append_heading(sheet_data, 4, table_1_title)
    after_table_1 = _append_block(sheet_data, 5, HIGH_HEADERS, station_rows)

    table_2_start = after_table_1 + 1
    _append_heading(sheet_data, table_2_start, table_2_title)
    _append_heading(sheet_data, table_2_start + 1, high_label)
    after_pv_high = _append_block(sheet_data, table_2_start + 2, HIGH_HEADERS, pv_high_rows)
    _append_heading(sheet_data, after_pv_high, low_label)
    after_pv_low = _append_block(sheet_data, after_pv_high + 1, LOW_HEADERS, pv_low_rows)
    note_row = after_pv_low + 1
    _append_row(
        sheet_data,
        note_row,
        [_inline_string_cell("A" + str(note_row), "注：低压侧不计算单相接地短路电流；两相短路电流按 0.866×三相短路电流计算。", 1)],
        height=19,
    )

    merge_refs = ["A1:D1", "A2:D2", "A4:D4", f"A{table_2_start}:D{table_2_start}", f"A{table_2_start + 1}:D{table_2_start + 1}", f"A{after_pv_high}:D{after_pv_high}", f"A{note_row}:D{note_row}"]
    merge_cells = ET.SubElement(worksheet, _q(_MAIN_NS, "mergeCells"), {"count": str(len(merge_refs))})
    for reference in merge_refs:
        ET.SubElement(merge_cells, _q(_MAIN_NS, "mergeCell"), {"ref": reference})

    page_margins = ET.SubElement(worksheet, _q(_MAIN_NS, "pageMargins"))
    page_margins.attrib.update({"left": "0.4", "right": "0.4", "top": "0.6", "bottom": "0.6", "header": "0.3", "footer": "0.3"})
    return ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)


def _styles_xml() -> bytes:
    styles = ET.Element(_q(_MAIN_NS, "styleSheet"))
    num_fmts = ET.SubElement(styles, _q(_MAIN_NS, "numFmts"), {"count": "1"})
    ET.SubElement(num_fmts, _q(_MAIN_NS, "numFmt"), {"numFmtId": "164", "formatCode": "0.000"})
    fonts = ET.SubElement(styles, _q(_MAIN_NS, "fonts"), {"count": "2"})
    ET.SubElement(fonts, _q(_MAIN_NS, "font"))
    bold = ET.SubElement(fonts, _q(_MAIN_NS, "font"))
    ET.SubElement(bold, _q(_MAIN_NS, "b"))
    fills = ET.SubElement(styles, _q(_MAIN_NS, "fills"), {"count": "2"})
    ET.SubElement(ET.SubElement(fills, _q(_MAIN_NS, "fill")), _q(_MAIN_NS, "patternFill"), {"patternType": "none"})
    ET.SubElement(ET.SubElement(fills, _q(_MAIN_NS, "fill")), _q(_MAIN_NS, "patternFill"), {"patternType": "gray125"})
    borders = ET.SubElement(styles, _q(_MAIN_NS, "borders"), {"count": "2"})
    ET.SubElement(borders, _q(_MAIN_NS, "border"))
    border = ET.SubElement(borders, _q(_MAIN_NS, "border"))
    for side in ("left", "right", "top", "bottom"):
        ET.SubElement(border, _q(_MAIN_NS, side), {"style": "thin"})
    ET.SubElement(styles, _q(_MAIN_NS, "cellStyleXfs"), {"count": "1"}).append(ET.Element(_q(_MAIN_NS, "xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"}))
    cell_xfs = ET.SubElement(styles, _q(_MAIN_NS, "cellXfs"), {"count": "4"})
    ET.SubElement(cell_xfs, _q(_MAIN_NS, "xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})

    def centered(*, num_fmt: str = "0", font: str = "0") -> None:
        attrs = {"numFmtId": num_fmt, "fontId": font, "fillId": "0", "borderId": "1", "xfId": "0", "applyAlignment": "1"}
        if num_fmt != "0":
            attrs["applyNumberFormat"] = "1"
        xf = ET.SubElement(cell_xfs, _q(_MAIN_NS, "xf"), attrs)
        ET.SubElement(xf, _q(_MAIN_NS, "alignment"), {"horizontal": "center", "vertical": "center", "wrapText": "1"})

    centered()
    centered(num_fmt="164")
    centered(font="1")
    ET.SubElement(styles, _q(_MAIN_NS, "cellStyles"), {"count": "1"}).append(ET.Element(_q(_MAIN_NS, "cellStyle"), {"name": "Normal", "xfId": "0", "builtinId": "0"}))
    return ET.tostring(styles, encoding="utf-8", xml_declaration=True)


def _workbook_xml() -> bytes:
    workbook = ET.Element(_q(_MAIN_NS, "workbook"))
    sheets = ET.SubElement(workbook, _q(_MAIN_NS, "sheets"))
    ET.SubElement(sheets, _q(_MAIN_NS, "sheet"), {"name": "短路电流结果", "sheetId": "1", _q(_DOC_REL_NS, "id"): "rId1"})
    return ET.tostring(workbook, encoding="utf-8", xml_declaration=True)


def _content_types_xml() -> bytes:
    return b'''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''


def _relationships_xml() -> bytes:
    return b'''<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="/xl/workbook.xml"/>
</Relationships>'''


def _workbook_relationships_xml() -> bytes:
    return b'''<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''


def export_result_workbook(output_path: str | Path, result: CalculationResult) -> Path:
    """Write scenario-aware final result tables to an Excel workbook."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, mode="w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _content_types_xml())
        workbook.writestr("_rels/.rels", _relationships_xml())
        workbook.writestr("xl/workbook.xml", _workbook_xml())
        workbook.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml())
        workbook.writestr("xl/styles.xml", _styles_xml())
        workbook.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(result))
    return path
