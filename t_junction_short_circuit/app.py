"""Tkinter desktop application for the PV short-circuit calculator."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .calculator import (
    DESIGN_SCENARIO_DIRECT_CONNECTION,
    DESIGN_SCENARIO_T_CONNECTION,
    PV_INPUT_MODE_ACTIVE_POWER_PF,
    PV_INPUT_MODE_APPARENT_POWER,
    CalculationResult,
    calculate,
)
from .excel_export import export_result_workbook
from .input_adapter import build_inputs
from .presentation import (
    HIGH_VOLTAGE_RESULT_TABLE_HEADERS,
    LOW_VOLTAGE_RESULT_TABLE_HEADERS,
    build_detail_text,
    build_result_tables,
)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    unit: str
    default: str
    is_text: bool = False


@dataclass
class FieldWidgets:
    label: ttk.Label
    entry: ttk.Entry
    unit: ttk.Label


PV_MODE_ACTIVE_POWER_PF = PV_INPUT_MODE_ACTIVE_POWER_PF
PV_MODE_APPARENT_POWER = PV_INPUT_MODE_APPARENT_POWER
PV_SECTION_TITLE = "2. 光伏电站参数"
DESIGN_SCENARIO_T = DESIGN_SCENARIO_T_CONNECTION
DESIGN_SCENARIO_DIRECT = DESIGN_SCENARIO_DIRECT_CONNECTION

DEFAULT_INPUT_PANE_WIDTH = 620
MIN_INPUT_PANE_WIDTH = 560
MIN_RESULT_PANE_WIDTH = 710
PV_DIRECT_INPUT_MODE_LABEL = "直接输入"
SPLITTER_OPAQUE_RESIZE = False
PANE_RESIZE_DEBOUNCE_MS = 60

HIGH_RESULT_COLUMN_MIN_WIDTHS = (220, 145, 165, 175)
HIGH_RESULT_COLUMN_WEIGHTS = (34, 20, 21, 25)
LOW_RESULT_COLUMN_MIN_WIDTHS = (260, 180, 180)
LOW_RESULT_COLUMN_WEIGHTS = (42, 29, 29)

BASE_FIELDS = (
    FieldSpec("high_rated_kv", "高压侧额定电压", "kV", "110"),
    FieldSpec("high_base_kv", "高压侧基准电压", "kV", "115"),
    FieldSpec("low_rated_kv", "低压侧额定电压", "kV", "35"),
    FieldSpec("low_base_kv", "低压侧基准电压", "kV", "37"),
    FieldSpec("base_mva", "基准容量", "MVA", "100"),
)
PV_STATION_NAME_FIELD = FieldSpec(
    "pv_station_name", "光伏电站名称", "", "光伏升压站", is_text=True
)
PV_ACTIVE_POWER_FIELDS = (
    FieldSpec("pv_active_mw", "光伏额定有功", "MW", "40"),
    FieldSpec("pv_power_factor", "功率因数", "—", "0.95"),
)
PV_APPARENT_POWER_FIELD = FieldSpec(
    "pv_apparent_mva_input", "光伏额定容量", "MVA", "42.105263"
)
SYSTEM_SOURCE_FIELDS = (
    FieldSpec("system_source_station_name", "变电站名称", "", "系统电源侧变电站", is_text=True),
    FieldSpec("system_source_x1_pu", "正序阻抗 XΣ", "p.u.", "0.0382"),
    FieldSpec("system_source_x0_pu", "零序阻抗 XΣ0", "p.u.", "0.0228"),
)
PV_NETWORK_FIELDS = (
    FieldSpec("line_reactance_ohm_per_km", "架空线路单位电抗", "Ω/km", "0.41"),
    FieldSpec("pv_to_connection_length_km", "光伏站至 T 接点长度", "km", "0.88"),
    FieldSpec("connection_to_system_source_length_km", "T 接点至系统电源侧变电站长度", "km", "7.89"),
    FieldSpec("transformer_uk_percent", "变压器短路电压百分比", "%", "10.5"),
    FieldSpec("transformer_rating_mva", "变压器额定容量", "MVA", "50"),
)
T_OPPOSITE_FIELDS = (
    FieldSpec("t_opposite_station_name", "变电站名称", "", "T接对侧变电站", is_text=True),
    FieldSpec("t_opposite_x1_pu", "正序阻抗 XΣ", "p.u.", "0.0664"),
    FieldSpec("t_opposite_x0_pu", "零序阻抗 XΣ0", "p.u.", "0.0902"),
)
ALL_FIELD_SPECS = (
    *BASE_FIELDS,
    PV_STATION_NAME_FIELD,
    *PV_ACTIVE_POWER_FIELDS,
    PV_APPARENT_POWER_FIELD,
    *SYSTEM_SOURCE_FIELDS,
    *PV_NETWORK_FIELDS,
    *T_OPPOSITE_FIELDS,
)
# Retained for lightweight configuration checks and external UI customisation.
SECTIONS = (
    ("1. 基准量与电压等级", BASE_FIELDS),
    (PV_SECTION_TITLE, (PV_STATION_NAME_FIELD,)),
)


def wrap_display_text(text: str, max_chars: int) -> str:
    """Wrap CJK display text without dropping visible characters."""

    if max_chars <= 0:
        return text
    lines: list[str] = []
    for source_line in text.split("\n"):
        lines.extend(source_line[start : start + max_chars] for start in range(0, len(source_line), max_chars))
    return "\n".join(lines)


def calculate_result_column_widths(
    total_width: int,
    minimum_widths: tuple[int, ...] = HIGH_RESULT_COLUMN_MIN_WIDTHS,
    weights: tuple[int, ...] = HIGH_RESULT_COLUMN_WEIGHTS,
) -> tuple[int, ...]:
    """Return readable proportional column widths for a responsive result table."""

    if len(minimum_widths) != len(weights):
        raise ValueError("列宽最小值和权重数量必须一致。")
    minimum_total = sum(minimum_widths)
    usable_width = max(total_width, minimum_total)
    extra_width = usable_width - minimum_total
    widths = [minimum + extra_width * weight // 100 for minimum, weight in zip(minimum_widths, weights)]
    widths[-1] += usable_width - sum(widths)
    return tuple(widths)


def _format_voltage_entry(value: str) -> str:
    """Show a valid typed value as a voltage level without disrupting editing."""

    raw = value.strip()
    if not raw:
        return "— kV"
    try:
        return f"{float(raw):g} kV"
    except ValueError:
        return f"{raw} kV"


def build_input_section_titles(high_voltage_text: str, low_voltage_text: str, pv_station_name: str) -> dict[str, str]:
    """Build scenario-independent input-section titles from the current entries."""

    high = _format_voltage_entry(high_voltage_text)
    low = _format_voltage_entry(low_voltage_text)
    pv_name = pv_station_name.strip() or "光伏升压站"
    return {
        "system_source": f"3. 系统电源侧变电站{high}侧",
        "pv_network": f"4. {pv_name}{high}、{low}侧",
        "t_opposite": f"5. T接对侧变电站{high}侧",
    }


class ScrollableFrame(ttk.Frame):
    """Dependency-free vertical scroll container for the parameter panel."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background="#F5F7FB", relief="flat")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, style="Panel.TFrame")
        self.content.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self._width_callback = None
        self.canvas.bind("<Configure>", self._resize_content)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.content.bind("<MouseWheel>", self._on_mousewheel)

    def set_width_callback(self, callback) -> None:
        self._width_callback = callback

    def _resize_content(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)
        if self._width_callback is not None:
            self._width_callback(event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")


class ResponsiveResultTable(tk.Frame):
    """Centered result table with dynamic column count, row count, and wrapping."""

    def __init__(
        self,
        parent: tk.Misc,
        headers: tuple[str, ...],
        minimum_widths: tuple[int, ...],
        weights: tuple[int, ...],
        body_font: tuple[str, int],
        header_font: tuple[str, int, str],
    ) -> None:
        super().__init__(parent, background="#D6DEE8", borderwidth=0, highlightthickness=0)
        self._headers = headers
        self._minimum_widths = minimum_widths
        self._weights = weights
        self._body_font = body_font
        self._header_font = header_font
        self._header_labels: list[tk.Label] = []
        self._row_labels: list[list[tk.Label]] = []
        self._last_width = 0
        self._last_column_widths: tuple[int, ...] | None = None

        for column, header in enumerate(headers):
            label = self._make_label(header, is_header=True)
            label.grid(row=0, column=column, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self._header_labels.append(label)
        self.bind("<Configure>", self._on_configure, add="+")
        self._apply_layout(sum(minimum_widths))

    def _make_label(self, text: str, *, is_header: bool) -> tk.Label:
        return tk.Label(
            self,
            text=text,
            font=self._header_font if is_header else self._body_font,
            foreground="#0F3A5B" if is_header else "#1E293B",
            background="#EFF6FF" if is_header else "#FFFFFF",
            anchor="center",
            justify="center",
            padx=8,
            pady=7,
            borderwidth=0,
            highlightthickness=0,
        )

    def _append_row(self) -> list[tk.Label]:
        row_index = len(self._row_labels) + 1
        labels: list[tk.Label] = []
        for column in range(len(self._headers)):
            label = self._make_label("", is_header=False)
            label.grid(row=row_index, column=column, sticky="nsew", padx=(0, 1), pady=(0, 1))
            labels.append(label)
        self._row_labels.append(labels)
        return labels

    def set_rows(self, rows: list[tuple[str, ...]]) -> None:
        while len(self._row_labels) < len(rows):
            self._append_row()
        for row_index, labels in enumerate(self._row_labels):
            if row_index < len(rows):
                for column, label in enumerate(labels):
                    label.configure(text=rows[row_index][column])
                    label.grid()
            else:
                for label in labels:
                    label.grid_remove()

    def _on_configure(self, event: tk.Event) -> None:
        if event.width != self._last_width:
            self._last_width = event.width
            self._apply_layout(event.width)

    def _apply_layout(self, total_width: int) -> None:
        widths = calculate_result_column_widths(total_width, self._minimum_widths, self._weights)
        if widths == self._last_column_widths:
            return
        self._last_column_widths = widths
        for column, width in enumerate(widths):
            self.columnconfigure(column, minsize=width, weight=self._weights[column])
        for row in range(len(self._row_labels) + 1):
            self.rowconfigure(row, weight=1)
        for column, width in enumerate(widths):
            for label in [self._header_labels[column], *(row[column] for row in self._row_labels)]:
                label.configure(wraplength=max(42, width - 16))


class ShortCircuitCalculatorApp(ttk.Frame):
    """The complete desktop UI. Numerical calculations stay in calculator.py."""

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=16, style="App.TFrame")
        self.root = root
        self.entries: dict[str, ttk.Entry] = {}
        self.field_widgets: dict[str, FieldWidgets] = {}
        self.input_field_labels: list[ttk.Label] = []
        self.section_frames: dict[str, ttk.LabelFrame] = {}
        self.pv_mode_label: ttk.Label | None = None
        self.pv_input_mode = tk.StringVar(master=root, value=PV_MODE_ACTIVE_POWER_PF)
        self.design_scenario = tk.StringVar(master=root, value=DESIGN_SCENARIO_T)
        self.pv_power_fields: ttk.Frame | None = None
        self.pv_capacity_field: ttk.Frame | None = None
        self.connection_to_source_widgets: FieldWidgets | None = None
        self.last_result: CalculationResult | None = None

        self._input_wrap_after_id: str | None = None
        self._pending_input_content_width = 0
        self._last_input_label_wraplength: int | None = None
        self._last_pv_mode_wraplength: int | None = None
        self._result_wrap_after_id: str | None = None
        self._pending_result_width = 0
        self._last_summary_wraplength: int | None = None

        self._configure_root()
        self._build_ui()
        self.calculate_and_show()

    def _configure_root(self) -> None:
        self.root.title("短路电流计算")
        self.root.minsize(1300, 780)
        self.root.geometry("1520x900")
        self.root.configure(background="#F5F7FB")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        font_family = "Microsoft YaHei UI" if os.name == "nt" else "Noto Sans CJK SC"
        self.body_font = (font_family, 10)
        self.body_bold_font = (font_family, 10, "bold")
        self.detail_font = (font_family, 10)
        style.configure(".", font=self.body_font, foreground="#1E293B")
        style.configure("App.TFrame", background="#F5F7FB")
        style.configure("Panel.TFrame", background="#F5F7FB")
        style.configure("TFrame", background="#F5F7FB")
        style.configure("TLabel", background="#F5F7FB", foreground="#1E293B")
        style.configure("Title.TLabel", font=(font_family, 18, "bold"), foreground="#102A43")
        style.configure("SubTitle.TLabel", font=(font_family, 10), foreground="#52657A")
        style.configure("Summary.TLabel", font=self.body_font, foreground="#1D4ED8")
        style.configure("Field.TLabel", font=self.body_font, foreground="#334155")
        style.configure("Unit.TLabel", font=self.body_font, foreground="#64748B")
        style.configure("ResultCaption.TLabel", font=self.body_bold_font, background="#FFFFFF", foreground="#0F3A5B")
        style.configure("SectionContent.TFrame", background="#FFFFFF")
        style.configure("Section.TRadiobutton", background="#FFFFFF", foreground="#334155")
        style.map("Section.TRadiobutton", foreground=[("active", "#1D4ED8")])
        style.configure("Section.TLabelframe", background="#FFFFFF", bordercolor="#D6DEE8", relief="solid")
        style.configure("Section.TLabelframe.Label", background="#FFFFFF", foreground="#0F3A5B", font=self.body_bold_font)
        style.configure("TEntry", fieldbackground="#FFFFFF", foreground="#0F172A", bordercolor="#B8C5D3", lightcolor="#B8C5D3", darkcolor="#B8C5D3", padding=(8, 5))
        style.map("TEntry", bordercolor=[("focus", "#2563EB")], lightcolor=[("focus", "#2563EB")], darkcolor=[("focus", "#2563EB")])
        style.configure("TButton", font=self.body_bold_font, padding=(14, 8))
        style.configure("Primary.TButton", background="#2563EB", foreground="#FFFFFF", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#1D4ED8"), ("pressed", "#1E40AF")])
        style.configure("Secondary.TButton", background="#FFFFFF", foreground="#1E3A5F", borderwidth=1)
        style.map("Secondary.TButton", background=[("active", "#EAF2FF")])
        style.configure("Export.TButton", background="#0F766E", foreground="#FFFFFF", borderwidth=0)
        style.map("Export.TButton", background=[("active", "#0B5E57"), ("pressed", "#064E3B")])

    def _build_ui(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="短路电流计算", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="按工程设计流程计算 T 接或直接接入方案下的系统总短路电流。", style="SubTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        actions = ttk.Frame(header, style="App.TFrame")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(actions, text="计算并更新结果", style="Primary.TButton", command=self.calculate_and_show).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="导出结果到 Excel", style="Export.TButton", command=self.export_to_excel).grid(row=0, column=1)

        self.split_pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, background="#D6DEE8", borderwidth=0, relief="flat", sashwidth=8, sashpad=4, sashrelief="raised", sashcursor="sb_h_double_arrow", opaqueresize=SPLITTER_OPAQUE_RESIZE)
        self.split_pane.grid(row=1, column=0, sticky="nsew")
        input_holder = self._build_input_panel(self.split_pane)
        result_holder = self._build_result_panel(self.split_pane)
        self.split_pane.add(input_holder, minsize=MIN_INPUT_PANE_WIDTH, stretch="never")
        self.split_pane.add(result_holder, minsize=MIN_RESULT_PANE_WIDTH, stretch="always")
        self.after_idle(self._place_default_splitter)

    def _place_default_splitter(self) -> None:
        total_width = self.split_pane.winfo_width()
        if total_width <= 1:
            self.after(80, self._place_default_splitter)
            return
        maximum_left = max(MIN_INPUT_PANE_WIDTH, total_width - MIN_RESULT_PANE_WIDTH)
        self.split_pane.sash_place(0, min(DEFAULT_INPUT_PANE_WIDTH, maximum_left), 0)

    @staticmethod
    def _setup_three_column_section(section: ttk.LabelFrame) -> None:
        section.columnconfigure(0, minsize=170, weight=0)
        section.columnconfigure(1, minsize=185, weight=1)
        section.columnconfigure(2, minsize=64, weight=0)

    def _build_input_panel(self, parent: tk.Misc) -> ttk.Frame:
        holder = ttk.Frame(parent, style="Panel.TFrame")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        scroll = ScrollableFrame(holder)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.content.columnconfigure(0, weight=1)
        scroll.set_width_callback(self._update_input_wraplengths)

        scenario_section = ttk.LabelFrame(scroll.content, text="0. 设计情形", style="Section.TLabelframe", padding=12)
        scenario_section.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        scenario_section.columnconfigure(1, weight=1)
        ttk.Label(scenario_section, text="接入方式", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        mode_frame = ttk.Frame(scenario_section, style="SectionContent.TFrame")
        mode_frame.grid(row=0, column=1, sticky="ew", padx=(12, 0))
        ttk.Radiobutton(mode_frame, text="T接接入", value=DESIGN_SCENARIO_T, variable=self.design_scenario, command=self._toggle_design_scenario, style="Section.TRadiobutton").grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Radiobutton(mode_frame, text="直接接入", value=DESIGN_SCENARIO_DIRECT, variable=self.design_scenario, command=self._toggle_design_scenario, style="Section.TRadiobutton").grid(row=0, column=1, sticky="w")

        base = ttk.LabelFrame(scroll.content, text="1. 基准量与电压等级", style="Section.TLabelframe", padding=12)
        base.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self._setup_three_column_section(base)
        for row, field in enumerate(BASE_FIELDS):
            self._add_input_field(base, row, field)

        pv = ttk.LabelFrame(scroll.content, text=PV_SECTION_TITLE, style="Section.TLabelframe", padding=12)
        pv.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self._setup_three_column_section(pv)
        self._build_pv_input_section(pv)

        source = ttk.LabelFrame(scroll.content, text="3. 系统电源侧变电站110 kV侧", style="Section.TLabelframe", padding=12)
        source.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self._setup_three_column_section(source)
        self.section_frames["system_source"] = source
        for row, field in enumerate(SYSTEM_SOURCE_FIELDS):
            self._add_input_field(source, row, field)

        pv_network = ttk.LabelFrame(scroll.content, text="4. 光伏升压站110 kV、35 kV侧", style="Section.TLabelframe", padding=12)
        pv_network.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self._setup_three_column_section(pv_network)
        self.section_frames["pv_network"] = pv_network
        for row, field in enumerate(PV_NETWORK_FIELDS):
            widgets = self._add_input_field(pv_network, row, field)
            if field.key == "connection_to_system_source_length_km":
                self.connection_to_source_widgets = widgets

        opposite = ttk.LabelFrame(scroll.content, text="5. T接对侧变电站110 kV侧", style="Section.TLabelframe", padding=12)
        opposite.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self._setup_three_column_section(opposite)
        self.section_frames["t_opposite"] = opposite
        for row, field in enumerate(T_OPPOSITE_FIELDS):
            self._add_input_field(opposite, row, field)

        buttons = ttk.Frame(scroll.content, style="Panel.TFrame")
        buttons.grid(row=6, column=0, sticky="ew", pady=(2, 14))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="计算短路电流", style="Primary.TButton", command=self.calculate_and_show).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="恢复示例参数", style="Secondary.TButton", command=self.restore_defaults).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        for key in ("high_rated_kv", "low_rated_kv", "pv_station_name"):
            self.entries[key].bind("<KeyRelease>", self._refresh_dynamic_section_titles, add="+")
            self.entries[key].bind("<FocusOut>", self._refresh_dynamic_section_titles, add="+")
        self._toggle_design_scenario()
        return holder

    def _update_input_wraplengths(self, content_width: int) -> None:
        self._pending_input_content_width = content_width
        if self._input_wrap_after_id is not None:
            self.after_cancel(self._input_wrap_after_id)
        self._input_wrap_after_id = self.after(PANE_RESIZE_DEBOUNCE_MS, self._apply_pending_input_wraplengths)

    def _apply_pending_input_wraplengths(self) -> None:
        self._input_wrap_after_id = None
        label_width = max(120, min(195, int(self._pending_input_content_width * 0.34)))
        if label_width != self._last_input_label_wraplength:
            self._last_input_label_wraplength = label_width
            for label in self.input_field_labels:
                label.configure(wraplength=label_width)
        pv_mode_wraplength = max(180, self._pending_input_content_width - 32)
        if self.pv_mode_label is not None and pv_mode_wraplength != self._last_pv_mode_wraplength:
            self._last_pv_mode_wraplength = pv_mode_wraplength
            self.pv_mode_label.configure(wraplength=pv_mode_wraplength)

    def _add_input_field(self, parent: ttk.Frame, row: int, field: FieldSpec) -> FieldWidgets:
        label = ttk.Label(parent, text=field.label, style="Field.TLabel", anchor="w", justify="left", wraplength=170)
        label.grid(row=row, column=0, sticky="ew", pady=5)
        self.input_field_labels.append(label)
        entry = ttk.Entry(parent, justify="left" if field.is_text else "right", width=16)
        entry.insert(0, field.default)
        entry.grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=5)
        unit = ttk.Label(parent, text=field.unit, style="Unit.TLabel", width=7)
        unit.grid(row=row, column=2, sticky="w", pady=5)
        widgets = FieldWidgets(label, entry, unit)
        self.entries[field.key] = entry
        self.field_widgets[field.key] = widgets
        return widgets

    def _build_pv_input_section(self, section: ttk.LabelFrame) -> None:
        self._add_input_field(section, 0, PV_STATION_NAME_FIELD)
        self.pv_mode_label = ttk.Label(section, text="额定容量输入方式", style="Field.TLabel", anchor="w", justify="left", wraplength=300)
        self.pv_mode_label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        mode_frame = ttk.Frame(section, style="SectionContent.TFrame")
        mode_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        mode_frame.columnconfigure(0, weight=1)
        mode_frame.columnconfigure(1, weight=0)
        ttk.Radiobutton(mode_frame, text="由额定有功和功率因数计算", value=PV_MODE_ACTIVE_POWER_PF, variable=self.pv_input_mode, command=self._toggle_pv_input_mode, style="Section.TRadiobutton").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Radiobutton(mode_frame, text=PV_DIRECT_INPUT_MODE_LABEL, value=PV_MODE_APPARENT_POWER, variable=self.pv_input_mode, command=self._toggle_pv_input_mode, style="Section.TRadiobutton").grid(row=0, column=1, sticky="e")
        self.pv_power_fields = ttk.Frame(section, style="SectionContent.TFrame")
        self.pv_power_fields.grid(row=3, column=0, columnspan=3, sticky="ew")
        self._setup_three_column_section(self.pv_power_fields)
        for row, field in enumerate(PV_ACTIVE_POWER_FIELDS):
            self._add_input_field(self.pv_power_fields, row, field)
        self.pv_capacity_field = ttk.Frame(section, style="SectionContent.TFrame")
        self.pv_capacity_field.grid(row=3, column=0, columnspan=3, sticky="ew")
        self._setup_three_column_section(self.pv_capacity_field)
        self._add_input_field(self.pv_capacity_field, 0, PV_APPARENT_POWER_FIELD)
        self._toggle_pv_input_mode()

    def _toggle_pv_input_mode(self) -> None:
        if self.pv_power_fields is None or self.pv_capacity_field is None:
            return
        if self.pv_input_mode.get() == PV_MODE_ACTIVE_POWER_PF:
            self.pv_power_fields.grid()
            self.pv_capacity_field.grid_remove()
        else:
            self.pv_power_fields.grid_remove()
            self.pv_capacity_field.grid()

    def _toggle_design_scenario(self) -> None:
        is_t = self.design_scenario.get() == DESIGN_SCENARIO_T
        if is_t:
            self.section_frames["t_opposite"].grid()
            self._show_field_widgets(self.connection_to_source_widgets)
            self.field_widgets["pv_to_connection_length_km"].label.configure(text="光伏站至 T 接点长度")
        else:
            self.section_frames["t_opposite"].grid_remove()
            self._hide_field_widgets(self.connection_to_source_widgets)
            self.field_widgets["pv_to_connection_length_km"].label.configure(text="光伏站至系统电源侧变电站线路长度")
        self._refresh_dynamic_section_titles()

    @staticmethod
    def _show_field_widgets(widgets: FieldWidgets | None) -> None:
        if widgets is not None:
            widgets.label.grid()
            widgets.entry.grid()
            widgets.unit.grid()

    @staticmethod
    def _hide_field_widgets(widgets: FieldWidgets | None) -> None:
        if widgets is not None:
            widgets.label.grid_remove()
            widgets.entry.grid_remove()
            widgets.unit.grid_remove()

    def _refresh_dynamic_section_titles(self, _event: tk.Event | None = None) -> None:
        titles = build_input_section_titles(
            self.entries["high_rated_kv"].get(),
            self.entries["low_rated_kv"].get(),
            self.entries["pv_station_name"].get(),
        )
        for key, title in titles.items():
            self.section_frames[key].configure(text=title)

    def _build_result_panel(self, parent: tk.Misc) -> ttk.Frame:
        holder = ttk.Frame(parent, style="App.TFrame")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(3, weight=1)
        self.summary_var = tk.StringVar(value="输入参数后点击“计算短路电流”。")
        self.summary_label = ttk.Label(holder, textvariable=self.summary_var, style="Summary.TLabel", anchor="w", justify="left", wraplength=640)
        self.summary_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        holder.bind("<Configure>", self._update_result_wraplengths, add="+")

        self.station_table = ttk.LabelFrame(holder, text="表 1  变电站系统总短路电流（kA）", style="Section.TLabelframe", padding=10)
        self.station_table.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.station_table.columnconfigure(0, weight=1)
        self.station_result_table = self._make_result_table(self.station_table, HIGH_VOLTAGE_RESULT_TABLE_HEADERS, HIGH_RESULT_COLUMN_MIN_WIDTHS, HIGH_RESULT_COLUMN_WEIGHTS)
        self.station_result_table.grid(row=0, column=0, sticky="ew")

        self.pv_table = ttk.LabelFrame(holder, text="表 2  光伏升压站系统总短路电流（kA）", style="Section.TLabelframe", padding=10)
        self.pv_table.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.pv_table.columnconfigure(0, weight=1)
        self.pv_high_caption = ttk.Label(self.pv_table, text="光伏升压站高压侧", style="ResultCaption.TLabel", anchor="center", justify="center")
        self.pv_high_caption.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.pv_high_result_table = self._make_result_table(self.pv_table, HIGH_VOLTAGE_RESULT_TABLE_HEADERS, HIGH_RESULT_COLUMN_MIN_WIDTHS, HIGH_RESULT_COLUMN_WEIGHTS)
        self.pv_high_result_table.grid(row=1, column=0, sticky="ew")
        self.pv_low_caption = ttk.Label(self.pv_table, text="光伏升压站低压侧", style="ResultCaption.TLabel", anchor="center", justify="center")
        self.pv_low_caption.grid(row=2, column=0, sticky="ew", pady=(9, 4))
        self.pv_low_result_table = self._make_result_table(self.pv_table, LOW_VOLTAGE_RESULT_TABLE_HEADERS, LOW_RESULT_COLUMN_MIN_WIDTHS, LOW_RESULT_COLUMN_WEIGHTS)
        self.pv_low_result_table.grid(row=3, column=0, sticky="ew")

        details = ttk.LabelFrame(holder, text="计算中间量", style="Section.TLabelframe", padding=10)
        details.grid(row=3, column=0, sticky="nsew")
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.detail_text = tk.Text(details, height=18, font=self.detail_font, wrap="word", state="disabled", relief="flat", highlightthickness=0, background="#FFFFFF", foreground="#1E293B", insertbackground="#1E293B", padx=8, pady=8, spacing1=2, spacing3=3)
        scrollbar = ttk.Scrollbar(details, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=scrollbar.set)
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return holder

    def _update_result_wraplengths(self, event: tk.Event) -> None:
        self._pending_result_width = event.width
        if self._result_wrap_after_id is not None:
            self.after_cancel(self._result_wrap_after_id)
        self._result_wrap_after_id = self.after(PANE_RESIZE_DEBOUNCE_MS, self._apply_pending_result_wraplength)

    def _apply_pending_result_wraplength(self) -> None:
        self._result_wrap_after_id = None
        wraplength = max(260, self._pending_result_width - 12)
        if wraplength != self._last_summary_wraplength:
            self._last_summary_wraplength = wraplength
            self.summary_label.configure(wraplength=wraplength)

    def _make_result_table(self, parent: ttk.Frame, headers: tuple[str, ...], widths: tuple[int, ...], weights: tuple[int, ...]) -> ResponsiveResultTable:
        return ResponsiveResultTable(parent, headers, widths, weights, self.body_font, self.body_bold_font)

    def _input_values(self) -> dict[str, str]:
        values = {key: entry.get() for key, entry in self.entries.items()}
        values["pv_input_mode"] = self.pv_input_mode.get()
        values["design_scenario"] = self.design_scenario.get()
        return values

    def _set_detail_text(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    @staticmethod
    def _format_voltage(value: float) -> str:
        return f"{value:g} kV"

    def _update_table_titles(self, result: CalculationResult) -> None:
        high = self._format_voltage(result.system_source_station_high.voltage_kv)
        low = self._format_voltage(result.pv_station_low.voltage_kv)
        if result.t_opposite_station_high is None:
            self.station_table.configure(text=f"表 1  系统电源侧变电站{high}侧系统总短路电流（kA）")
        else:
            self.station_table.configure(text=f"表 1  T 接两侧变电站{high}侧系统总短路电流（kA）")
        self.pv_table.configure(text=f"表 2  {result.pv_station_name}系统总短路电流（kA）")
        self.pv_high_caption.configure(text=f"{result.pv_station_name}{high}侧")
        self.pv_low_caption.configure(text=f"{result.pv_station_name}{low}侧")

    def calculate_and_show(self) -> None:
        try:
            inputs = build_inputs(self._input_values())
            result = calculate(inputs)
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc), parent=self.root)
            return
        self.last_result = result
        station_rows, pv_high_rows, pv_low_rows = build_result_tables(result)
        self.station_result_table.set_rows(station_rows)
        self.pv_high_result_table.set_rows(pv_high_rows)
        self.pv_low_result_table.set_rows(pv_low_rows)
        self._update_table_titles(result)
        self._set_detail_text(build_detail_text(result))
        names = [result.system_source_station_high.label]
        if result.t_opposite_station_high is not None:
            names.append(result.t_opposite_station_high.label)
        self.summary_var.set(f"计算完成：{'、'.join(names)}；所有短路电流结果单位均为 kA。")

    def export_to_excel(self) -> None:
        if self.last_result is None:
            messagebox.showwarning("尚未计算", "请先完成短路电流计算，再导出 Excel。", parent=self.root)
            return
        output = filedialog.asksaveasfilename(parent=self.root, title="导出短路电流计算结果", defaultextension=".xlsx", initialfile="短路电流计算.xlsx", filetypes=(("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")))
        if not output:
            return
        try:
            saved_path = export_result_workbook(Path(output), self.last_result)
        except OSError as exc:
            messagebox.showerror("导出失败", f"无法写入 Excel 文件：\n{exc}", parent=self.root)
            return
        messagebox.showinfo("导出完成", f"已导出计算结果：\n{saved_path}", parent=self.root)

    def restore_defaults(self) -> None:
        defaults = {field.key: field.default for field in ALL_FIELD_SPECS}
        for key, entry in self.entries.items():
            entry.delete(0, "end")
            entry.insert(0, defaults[key])
        self.design_scenario.set(DESIGN_SCENARIO_T)
        self.pv_input_mode.set(PV_MODE_ACTIVE_POWER_PF)
        self._toggle_pv_input_mode()
        self._toggle_design_scenario()
        self.calculate_and_show()


def _enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main() -> None:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    ShortCircuitCalculatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
