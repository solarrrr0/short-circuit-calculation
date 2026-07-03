"""Short-circuit current engine for PV T-junction and direct interconnection.

All impedance-like values accepted by the public API are per-unit values unless
explicitly labelled otherwise. Currents returned by this module are kA.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

SQRT3 = sqrt(3.0)
PV_FAULT_MULTIPLIER = 1.5
LOW_SIDE_TWO_PHASE_FACTOR = 0.866
LINE_ZERO_SEQUENCE_RATIO = 2.5

PV_INPUT_MODE_ACTIVE_POWER_PF = "active_power_pf"
PV_INPUT_MODE_APPARENT_POWER = "apparent_power"
PV_INPUT_MODE_LABELS = {
    PV_INPUT_MODE_ACTIVE_POWER_PF: "由额定有功和功率因数计算",
    PV_INPUT_MODE_APPARENT_POWER: "直接输入额定容量",
}

DESIGN_SCENARIO_T_CONNECTION = "t_connection"
DESIGN_SCENARIO_DIRECT_CONNECTION = "direct_connection"
DESIGN_SCENARIO_LABELS = {
    DESIGN_SCENARIO_T_CONNECTION: "T接接入",
    DESIGN_SCENARIO_DIRECT_CONNECTION: "直接接入",
}


@dataclass(frozen=True)
class CalculationInputs:
    """Inputs for the selected PV interconnection design scenario."""

    high_rated_kv: float
    high_base_kv: float
    low_rated_kv: float
    low_base_kv: float
    base_mva: float

    pv_active_mw: float
    pv_power_factor: float

    system_source_x1_pu: float
    system_source_x0_pu: float

    line_reactance_ohm_per_km: float
    pv_to_connection_length_km: float
    connection_to_system_source_length_km: float

    transformer_uk_percent: float
    transformer_rating_mva: float

    t_opposite_x1_pu: float
    t_opposite_x0_pu: float

    pv_station_name: str = "光伏升压站"
    system_source_station_name: str = "系统电源侧变电站"
    t_opposite_station_name: str = "T接对侧变电站"
    design_scenario: str = DESIGN_SCENARIO_T_CONNECTION
    # The active-power fields are retained for compatibility. In direct-MVA
    # mode they are ignored and pv_apparent_mva_input is used instead.
    pv_input_mode: str = PV_INPUT_MODE_ACTIVE_POWER_PF
    pv_apparent_mva_input: float | None = None


@dataclass(frozen=True)
class GroundFaultResult:
    """A ≥110 kV result with three-, single-, and two-phase-ground faults."""

    label: str
    voltage_kv: float
    x1_pu: float
    x0_pu: float
    k0: float
    three_phase_short_circuit_coefficient: float
    single_phase_ground_short_circuit_coefficient: float
    two_phase_ground_coefficient: float
    three_phase_system_ka: float
    single_phase_system_ka: float
    two_phase_ground_system_ka: float
    three_phase_total_ka: float
    single_phase_total_ka: float
    two_phase_ground_total_ka: float
    line_total_length_km: float | None = None


@dataclass(frozen=True)
class LowSideResult:
    """Low-voltage station-side result. The workflow excludes single-phase faults."""

    label: str
    voltage_kv: float
    transformer_x_pu: float
    line_x1_pu: float
    x1_total_pu: float
    three_phase_short_circuit_coefficient: float
    three_phase_system_ka: float
    two_phase_system_ka: float
    three_phase_total_ka: float
    two_phase_total_ka: float


@dataclass(frozen=True)
class CalculationResult:
    """Complete package for the GUI, audit text, and Excel export."""

    base_current_high_ka: float
    base_current_low_ka: float
    base_impedance_high_ohm: float
    pv_apparent_mva: float
    pv_rated_current_high_ka: float
    pv_rated_current_low_ka: float
    pv_fault_current_high_ka: float
    pv_fault_current_low_ka: float
    pv_input_mode: str
    design_scenario: str
    pv_station_name: str
    system_source_station_high: GroundFaultResult
    pv_station_high: GroundFaultResult
    pv_station_low: LowSideResult
    t_opposite_station_high: GroundFaultResult | None


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name}必须大于 0。")


def _require_nonnegative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name}不能小于 0。")


def _validate(inputs: CalculationInputs) -> None:
    """Validate only values that belong to the selected design scenario."""

    positive_values = {
        "高压侧额定电压": inputs.high_rated_kv,
        "高压侧基准电压": inputs.high_base_kv,
        "低压侧额定电压": inputs.low_rated_kv,
        "低压侧基准电压": inputs.low_base_kv,
        "基准容量": inputs.base_mva,
        "系统电源侧正序阻抗": inputs.system_source_x1_pu,
        "架空线路单位电抗": inputs.line_reactance_ohm_per_km,
        "光伏站至接入点线路长度": inputs.pv_to_connection_length_km,
        "变压器短路电压百分比": inputs.transformer_uk_percent,
        "变压器额定容量": inputs.transformer_rating_mva,
    }
    for name, value in positive_values.items():
        _require_positive(name, value)

    scenario = inputs.design_scenario.strip()
    if scenario not in DESIGN_SCENARIO_LABELS:
        raise ValueError("设计情形无效。")

    pv_input_mode = inputs.pv_input_mode.strip()
    if pv_input_mode == PV_INPUT_MODE_ACTIVE_POWER_PF:
        _require_positive("光伏功率因数", inputs.pv_power_factor)
        if inputs.pv_power_factor > 1:
            raise ValueError("光伏功率因数必须不大于 1。")
        _require_nonnegative("光伏额定有功", inputs.pv_active_mw)
    elif pv_input_mode == PV_INPUT_MODE_APPARENT_POWER:
        if inputs.pv_apparent_mva_input is None:
            raise ValueError("请输入光伏额定容量。")
        _require_positive("光伏额定容量", inputs.pv_apparent_mva_input)
    else:
        raise ValueError("光伏额定容量输入方式无效。")

    _require_nonnegative("系统电源侧零序阻抗", inputs.system_source_x0_pu)

    if scenario == DESIGN_SCENARIO_T_CONNECTION:
        _require_nonnegative("T接点至系统电源侧变电站线路长度", inputs.connection_to_system_source_length_km)
        if inputs.pv_to_connection_length_km + inputs.connection_to_system_source_length_km <= 0:
            raise ValueError("两段架空线路的总长度必须大于 0。")
        _require_positive("T接对侧正序阻抗", inputs.t_opposite_x1_pu)
        _require_nonnegative("T接对侧零序阻抗", inputs.t_opposite_x0_pu)
        if not inputs.t_opposite_station_name.strip():
            raise ValueError("请输入T接对侧变电站名称。")

    if not inputs.pv_station_name.strip():
        raise ValueError("请输入光伏电站名称。")
    if not inputs.system_source_station_name.strip():
        raise ValueError("请输入系统电源侧变电站名称。")


def _base_current_ka(base_mva: float, base_kv: float) -> float:
    return base_mva / SQRT3 / base_kv


def _voltage_side_label(name: str, voltage_kv: float) -> str:
    """Return a calculation-point label using the user-entered voltage level."""

    return f"{name}{voltage_kv:g} kV侧"


def _ground_fault_result(
    *,
    label: str,
    voltage_kv: float,
    base_current_ka: float,
    x1_pu: float,
    x0_pu: float,
    pv_fault_current_ka: float,
    line_total_length_km: float | None = None,
) -> GroundFaultResult:
    """Compute the ≥110 kV fault quantities prescribed by the workflow."""

    _require_positive(f"{label}正序阻抗", x1_pu)
    _require_nonnegative(f"{label}零序阻抗", x0_pu)
    denominator = 2.0 * x1_pu + x0_pu
    _require_positive(f"{label}单相故障阻抗分母", denominator)

    k0 = x0_pu / x1_pu
    three_phase_short_circuit_coefficient = 1.0 / x1_pu
    single_phase_ground_short_circuit_coefficient = 3.0 / denominator
    two_phase_ground_coefficient = (
        SQRT3
        * sqrt((0.5 + k0) ** 2 + (SQRT3 / 2.0) ** 2)
        / (1.0 + 2.0 * k0)
    )

    three_phase_system_ka = base_current_ka * three_phase_short_circuit_coefficient
    single_phase_system_ka = base_current_ka * single_phase_ground_short_circuit_coefficient
    two_phase_ground_system_ka = two_phase_ground_coefficient * three_phase_system_ka

    return GroundFaultResult(
        label=label,
        voltage_kv=voltage_kv,
        x1_pu=x1_pu,
        x0_pu=x0_pu,
        k0=k0,
        three_phase_short_circuit_coefficient=three_phase_short_circuit_coefficient,
        single_phase_ground_short_circuit_coefficient=single_phase_ground_short_circuit_coefficient,
        two_phase_ground_coefficient=two_phase_ground_coefficient,
        three_phase_system_ka=three_phase_system_ka,
        single_phase_system_ka=single_phase_system_ka,
        two_phase_ground_system_ka=two_phase_ground_system_ka,
        three_phase_total_ka=three_phase_system_ka + pv_fault_current_ka,
        single_phase_total_ka=single_phase_system_ka + pv_fault_current_ka,
        two_phase_ground_total_ka=two_phase_ground_system_ka + pv_fault_current_ka,
        line_total_length_km=line_total_length_km,
    )


def calculate(inputs: CalculationInputs) -> CalculationResult:
    """Calculate the selected T-junction or direct-interconnection case.

    At the PV-station high-voltage fault point:

    * T-junction: ``X1 = X1,source + Xline(PV–T) + Xline(T–source)``.
    * Direct: ``X1 = X1,source + Xline(PV–source)``.

    In both cases, line zero-sequence reactance is ``2.5 × Xline`` while the
    system-source zero-sequence equivalent is added independently.
    """

    _validate(inputs)

    scenario = inputs.design_scenario.strip()
    base_current_high_ka = _base_current_ka(inputs.base_mva, inputs.high_base_kv)
    base_current_low_ka = _base_current_ka(inputs.base_mva, inputs.low_base_kv)
    base_impedance_high_ohm = inputs.high_base_kv**2 / inputs.base_mva

    pv_input_mode = inputs.pv_input_mode.strip()
    if pv_input_mode == PV_INPUT_MODE_ACTIVE_POWER_PF:
        pv_apparent_mva = inputs.pv_active_mw / inputs.pv_power_factor
    else:
        assert inputs.pv_apparent_mva_input is not None
        pv_apparent_mva = inputs.pv_apparent_mva_input

    pv_rated_current_high_ka = pv_apparent_mva / SQRT3 / inputs.high_rated_kv
    pv_rated_current_low_ka = pv_apparent_mva / SQRT3 / inputs.low_rated_kv
    pv_fault_current_high_ka = PV_FAULT_MULTIPLIER * pv_rated_current_high_ka
    pv_fault_current_low_ka = PV_FAULT_MULTIPLIER * pv_rated_current_low_ka

    system_source_station_high = _ground_fault_result(
        label=_voltage_side_label(inputs.system_source_station_name.strip(), inputs.high_rated_kv),
        voltage_kv=inputs.high_rated_kv,
        base_current_ka=base_current_high_ka,
        x1_pu=inputs.system_source_x1_pu,
        x0_pu=inputs.system_source_x0_pu,
        pv_fault_current_ka=pv_fault_current_high_ka,
    )

    if scenario == DESIGN_SCENARIO_T_CONNECTION:
        line_total_length_km = (
            inputs.pv_to_connection_length_km
            + inputs.connection_to_system_source_length_km
        )
    else:
        line_total_length_km = inputs.pv_to_connection_length_km

    line_x1_pu = (
        line_total_length_km * inputs.line_reactance_ohm_per_km / base_impedance_high_ohm
    )
    pv_station_x1_pu = inputs.system_source_x1_pu + line_x1_pu
    pv_station_x0_pu = inputs.system_source_x0_pu + LINE_ZERO_SEQUENCE_RATIO * line_x1_pu

    pv_station_high = _ground_fault_result(
        label=_voltage_side_label(inputs.pv_station_name.strip(), inputs.high_rated_kv),
        voltage_kv=inputs.high_rated_kv,
        base_current_ka=base_current_high_ka,
        x1_pu=pv_station_x1_pu,
        x0_pu=pv_station_x0_pu,
        pv_fault_current_ka=pv_fault_current_high_ka,
        line_total_length_km=line_total_length_km,
    )

    transformer_x_pu = (
        inputs.transformer_uk_percent * inputs.base_mva
        / (100.0 * inputs.transformer_rating_mva)
    )
    x1_total_pu = pv_station_x1_pu + transformer_x_pu
    three_phase_short_circuit_coefficient_low = 1.0 / x1_total_pu
    three_phase_system_low_ka = base_current_low_ka * three_phase_short_circuit_coefficient_low
    two_phase_system_low_ka = LOW_SIDE_TWO_PHASE_FACTOR * three_phase_system_low_ka
    pv_station_low = LowSideResult(
        label=_voltage_side_label(inputs.pv_station_name.strip(), inputs.low_rated_kv),
        voltage_kv=inputs.low_rated_kv,
        transformer_x_pu=transformer_x_pu,
        line_x1_pu=pv_station_x1_pu,
        x1_total_pu=x1_total_pu,
        three_phase_short_circuit_coefficient=three_phase_short_circuit_coefficient_low,
        three_phase_system_ka=three_phase_system_low_ka,
        two_phase_system_ka=two_phase_system_low_ka,
        three_phase_total_ka=three_phase_system_low_ka + pv_fault_current_low_ka,
        two_phase_total_ka=two_phase_system_low_ka + pv_fault_current_low_ka,
    )

    t_opposite_station_high: GroundFaultResult | None = None
    if scenario == DESIGN_SCENARIO_T_CONNECTION:
        t_opposite_station_high = _ground_fault_result(
            label=_voltage_side_label(inputs.t_opposite_station_name.strip(), inputs.high_rated_kv),
            voltage_kv=inputs.high_rated_kv,
            base_current_ka=base_current_high_ka,
            x1_pu=inputs.t_opposite_x1_pu,
            x0_pu=inputs.t_opposite_x0_pu,
            pv_fault_current_ka=pv_fault_current_high_ka,
        )

    return CalculationResult(
        base_current_high_ka=base_current_high_ka,
        base_current_low_ka=base_current_low_ka,
        base_impedance_high_ohm=base_impedance_high_ohm,
        pv_apparent_mva=pv_apparent_mva,
        pv_rated_current_high_ka=pv_rated_current_high_ka,
        pv_rated_current_low_ka=pv_rated_current_low_ka,
        pv_fault_current_high_ka=pv_fault_current_high_ka,
        pv_fault_current_low_ka=pv_fault_current_low_ka,
        pv_input_mode=pv_input_mode,
        design_scenario=scenario,
        pv_station_name=inputs.pv_station_name.strip(),
        system_source_station_high=system_source_station_high,
        pv_station_high=pv_station_high,
        pv_station_low=pv_station_low,
        t_opposite_station_high=t_opposite_station_high,
    )
