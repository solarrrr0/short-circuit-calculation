"""Convert GUI text fields into validated, scenario-aware calculation inputs."""

from __future__ import annotations

from collections.abc import Mapping

from .calculator import (
    DESIGN_SCENARIO_DIRECT_CONNECTION,
    DESIGN_SCENARIO_T_CONNECTION,
    PV_INPUT_MODE_ACTIVE_POWER_PF,
    PV_INPUT_MODE_APPARENT_POWER,
    CalculationInputs,
)

FIELD_LABELS: dict[str, str] = {
    "high_rated_kv": "高压侧额定电压",
    "high_base_kv": "高压侧基准电压",
    "low_rated_kv": "低压侧额定电压",
    "low_base_kv": "低压侧基准电压",
    "base_mva": "基准容量",
    "pv_active_mw": "光伏额定有功",
    "pv_power_factor": "光伏功率因数",
    "pv_apparent_mva_input": "光伏额定容量",
    "system_source_x1_pu": "系统电源侧正序阻抗 XΣ",
    "system_source_x0_pu": "系统电源侧零序阻抗 XΣ0",
    "line_reactance_ohm_per_km": "架空线路单位电抗",
    "pv_to_connection_length_km": "光伏站至接入点线路长度",
    "connection_to_system_source_length_km": "T接点至系统电源侧变电站线路长度",
    "transformer_uk_percent": "变压器短路电压百分比",
    "transformer_rating_mva": "变压器额定容量",
    "t_opposite_x1_pu": "T接对侧正序阻抗 XΣ",
    "t_opposite_x0_pu": "T接对侧零序阻抗 XΣ0",
}

TEXT_FIELD_LABELS: dict[str, str] = {
    "pv_station_name": "光伏电站名称",
    "system_source_station_name": "系统电源侧变电站名称",
    "t_opposite_station_name": "T接对侧变电站名称",
}

DEFAULT_STATION_NAMES = {
    "pv_station_name": "光伏升压站",
    "system_source_station_name": "系统电源侧变电站",
    "t_opposite_station_name": "T接对侧变电站",
}


def _parse_float(key: str, value: str) -> float:
    normalized = value.strip().replace("，", ",").replace(",", ".")
    if not normalized:
        raise ValueError(f"请输入{FIELD_LABELS[key]}。")
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"{FIELD_LABELS[key]}必须是有效数字。") from exc


def _parse_station_name(key: str, value: str | None) -> str:
    normalized = (DEFAULT_STATION_NAMES[key] if value is None else value).strip()
    if not normalized:
        raise ValueError(f"请输入{TEXT_FIELD_LABELS[key]}。")
    return normalized


def build_inputs(values: Mapping[str, str]) -> CalculationInputs:
    """Build calculation inputs, ignoring controls hidden by the selected scenario."""

    scenario = values.get("design_scenario", DESIGN_SCENARIO_T_CONNECTION).strip()
    if scenario not in {DESIGN_SCENARIO_T_CONNECTION, DESIGN_SCENARIO_DIRECT_CONNECTION}:
        raise ValueError("设计情形无效。")

    mode = values.get("pv_input_mode", PV_INPUT_MODE_ACTIVE_POWER_PF).strip()
    common_numeric_keys = (
        "high_rated_kv",
        "high_base_kv",
        "low_rated_kv",
        "low_base_kv",
        "base_mva",
        "system_source_x1_pu",
        "system_source_x0_pu",
        "line_reactance_ohm_per_km",
        "pv_to_connection_length_km",
        "transformer_uk_percent",
        "transformer_rating_mva",
    )
    parsed = {key: _parse_float(key, values.get(key, "")) for key in common_numeric_keys}

    if scenario == DESIGN_SCENARIO_T_CONNECTION:
        parsed.update(
            connection_to_system_source_length_km=_parse_float(
                "connection_to_system_source_length_km",
                values.get("connection_to_system_source_length_km", ""),
            ),
            t_opposite_x1_pu=_parse_float("t_opposite_x1_pu", values.get("t_opposite_x1_pu", "")),
            t_opposite_x0_pu=_parse_float("t_opposite_x0_pu", values.get("t_opposite_x0_pu", "")),
        )
    else:
        # The hidden T-junction-only controls must not block a direct case.
        parsed.update(
            connection_to_system_source_length_km=0.0,
            t_opposite_x1_pu=0.0,
            t_opposite_x0_pu=0.0,
        )

    if mode == PV_INPUT_MODE_ACTIVE_POWER_PF:
        parsed.update(
            pv_active_mw=_parse_float("pv_active_mw", values.get("pv_active_mw", "")),
            pv_power_factor=_parse_float("pv_power_factor", values.get("pv_power_factor", "")),
            pv_apparent_mva_input=None,
        )
    elif mode == PV_INPUT_MODE_APPARENT_POWER:
        parsed.update(
            pv_active_mw=0.0,
            pv_power_factor=1.0,
            pv_apparent_mva_input=_parse_float(
                "pv_apparent_mva_input", values.get("pv_apparent_mva_input", "")
            ),
        )
    else:
        raise ValueError("光伏额定容量输入方式无效。")

    names = {
        "pv_station_name": _parse_station_name("pv_station_name", values.get("pv_station_name")),
        "system_source_station_name": _parse_station_name(
            "system_source_station_name", values.get("system_source_station_name")
        ),
        "t_opposite_station_name": (
            _parse_station_name("t_opposite_station_name", values.get("t_opposite_station_name"))
            if scenario == DESIGN_SCENARIO_T_CONNECTION
            else DEFAULT_STATION_NAMES["t_opposite_station_name"]
        ),
    }
    return CalculationInputs(
        **parsed,
        **names,
        design_scenario=scenario,
        pv_input_mode=mode,
    )
