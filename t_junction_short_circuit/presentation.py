"""Formatting helpers shared by the desktop UI, audit text, and Excel export."""

from __future__ import annotations

from .calculator import (
    DESIGN_SCENARIO_LABELS,
    DESIGN_SCENARIO_T_CONNECTION,
    PV_INPUT_MODE_ACTIVE_POWER_PF,
    CalculationResult,
    GroundFaultResult,
)

HIGH_VOLTAGE_RESULT_TABLE_HEADERS = (
    "计算位置",
    "三相短路电流",
    "单相接地短路电流",
    "两相接地短路电流",
)
LOW_VOLTAGE_RESULT_TABLE_HEADERS = (
    "计算位置",
    "三相短路电流",
    "两相短路电流",
)
# Retained as the main high-voltage header alias for GUI consumers.
RESULT_TABLE_HEADERS = HIGH_VOLTAGE_RESULT_TABLE_HEADERS


def fmt(value: float) -> str:
    """Format final short-circuit-current table values to three decimal places."""

    return f"{value:.3f}"


def fmt_detail(value: float) -> str:
    """Format audit-trail intermediate quantities to six decimal places."""

    return f"{value:.6f}"


def _high_fault_row(item: GroundFaultResult) -> tuple[str, str, str, str]:
    return (
        item.label,
        fmt(item.three_phase_total_ka),
        fmt(item.single_phase_total_ka),
        fmt(item.two_phase_ground_total_ka),
    )


def build_result_tables(
    result: CalculationResult,
) -> tuple[
    list[tuple[str, str, str, str]],
    list[tuple[str, str, str, str]],
    list[tuple[str, str, str]],
]:
    """Return scenario-aware Table 1 and split high/low PV result blocks.

    Table 1 contains the system-source-side station and, only for T-junction
    interconnection, the T-junction opposite-side station.  Table 2 is split:
    the high-voltage block uses ground-fault columns while the low-voltage block
    reports the engineering two-phase short-circuit current.
    """

    station_rows = [_high_fault_row(result.system_source_station_high)]
    if result.t_opposite_station_high is not None:
        station_rows.append(_high_fault_row(result.t_opposite_station_high))

    pv_high_rows = [_high_fault_row(result.pv_station_high)]
    pv_low_rows = [
        (
            result.pv_station_low.label,
            fmt(result.pv_station_low.three_phase_total_ka),
            fmt(result.pv_station_low.two_phase_total_ka),
        )
    ]
    return station_rows, pv_high_rows, pv_low_rows


def build_detail_text(result: CalculationResult) -> str:
    """Build the engineering audit trail shown below the result tables."""

    source = result.system_source_station_high
    pvh = result.pv_station_high
    pvl = result.pv_station_low
    opposite = result.t_opposite_station_high

    def high_side_line(item: GroundFaultResult) -> str:
        return (
            f"  {item.label}：X1={fmt_detail(item.x1_pu)} p.u.，"
            f"X0={fmt_detail(item.x0_pu)} p.u.，"
            f"k0={fmt_detail(item.k0)}，"
            f"三相短路电流系数={fmt_detail(item.three_phase_short_circuit_coefficient)}，"
            f"单相接地短路电流系数={fmt_detail(item.single_phase_ground_short_circuit_coefficient)}，"
            f"两相接地短路电流系数={fmt_detail(item.two_phase_ground_coefficient)}"
        )

    high_voltage_level = f"{source.voltage_kv:g} kV"
    low_voltage_level = f"{pvl.voltage_kv:g} kV"
    line_x1_pu = pvh.x1_pu - source.x1_pu
    line_x0_pu = pvh.x0_pu - source.x0_pu
    pv_input_method = (
        "由额定有功和功率因数计算"
        if result.pv_input_mode == PV_INPUT_MODE_ACTIVE_POWER_PF
        else "直接输入额定容量"
    )
    scenario_name = DESIGN_SCENARIO_LABELS[result.design_scenario]

    lines = [
        "基础量与光伏贡献",
        f"  设计情形 = {scenario_name}",
        f"  {high_voltage_level}侧基准电流 Ij = {fmt_detail(result.base_current_high_ka)} kA",
        f"  {low_voltage_level}侧基准电流 Ij = {fmt_detail(result.base_current_low_ka)} kA",
        f"  {high_voltage_level}侧基准阻抗 Zj = {fmt_detail(result.base_impedance_high_ohm)} Ω",
        f"  光伏容量输入方式 = {pv_input_method}",
        f"  光伏额定容量 = {fmt_detail(result.pv_apparent_mva)} MVA",
        f"  {pvh.label}额定电流 = {fmt_detail(result.pv_rated_current_high_ka)} kA",
        f"  {pvl.label}额定电流 = {fmt_detail(result.pv_rated_current_low_ka)} kA",
        f"  {pvh.label}短路电流（1.5 倍额定电流）= {fmt_detail(result.pv_fault_current_high_ka)} kA",
        f"  {pvl.label}短路电流（1.5 倍额定电流）= {fmt_detail(result.pv_fault_current_low_ka)} kA",
        "",
        f"高压侧中间量（{high_voltage_level}）",
        high_side_line(source),
        (
            f"  {pvh.label}线路中间量：线路总长度={fmt_detail(pvh.line_total_length_km or 0.0)} km，"
            f"线路正序电抗={fmt_detail(line_x1_pu)} p.u.，"
            f"线路零序电抗（2.5×线路正序）={fmt_detail(line_x0_pu)} p.u."
        ),
        high_side_line(pvh),
    ]

    if opposite is not None:
        lines.append(high_side_line(opposite))

    lines.extend(
        [
            "",
            f"低压侧中间量（{low_voltage_level}）",
            (
                f"  {pvl.label}：变压器电抗 = {fmt_detail(pvl.transformer_x_pu)} p.u.；"
                f"{pvh.label}等值正序阻抗 = {fmt_detail(pvl.line_x1_pu)} p.u.；"
                f"{pvl.label}正序短路阻抗 = {fmt_detail(pvl.x1_total_pu)} p.u.；"
                f"三相短路电流系数 = {fmt_detail(pvl.three_phase_short_circuit_coefficient)}"
            ),
            "",
            "计算边界说明",
        ]
    )

    if result.design_scenario == DESIGN_SCENARIO_T_CONNECTION:
        lines.append(
            f"  {pvh.label}：XΣ = {source.label}正序阻抗 XΣ + 光伏站至T接点、T接点至系统电源侧变电站两段架空线路正序电抗；"
            f"XΣ0 = {source.label}零序阻抗 XΣ0 + 2.5×两段架空线路正序电抗。"
        )
    else:
        lines.append(
            f"  {pvh.label}：XΣ = {source.label}正序阻抗 XΣ + 光伏站至系统电源侧变电站架空线路正序电抗；"
            f"XΣ0 = {source.label}零序阻抗 XΣ0 + 2.5×该架空线路正序电抗。"
        )

    lines.append(
        f"  {pvl.label}不计算单相接地短路电流；两相短路电流按 0.866×三相短路电流计算。"
    )
    return "\n".join(lines)
