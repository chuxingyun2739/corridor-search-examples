from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class PerUnitBase:
    power_base_mva: float
    voltage_base_kv: float

    def __post_init__(self) -> None:
        if self.power_base_mva <= 0:
            raise ValueError("power_base_mva must be positive")
        if self.voltage_base_kv <= 0:
            raise ValueError("voltage_base_kv must be positive")

    @property
    def impedance_base_ohm(self) -> float:
        return self.voltage_base_kv**2 / self.power_base_mva

    @property
    def current_base_ka(self) -> float:
        return self.power_base_mva / (sqrt(3.0) * self.voltage_base_kv)


def to_pu_power(value: float, base: PerUnitBase, unit: str = "MW") -> float:
    if unit == "MW":
        mw = value
    elif unit == "kW":
        mw = value / 1000.0
    elif unit == "Mvar":
        mw = value
    elif unit == "kvar":
        mw = value / 1000.0
    else:
        raise ValueError(f"unsupported power unit: {unit}")
    return mw / base.power_base_mva


def from_pu_power(value_pu: float, base: PerUnitBase, unit: str = "MW") -> float:
    mw = value_pu * base.power_base_mva
    if unit in ("MW", "Mvar"):
        return mw
    if unit in ("kW", "kvar"):
        return mw * 1000.0
    raise ValueError(f"unsupported power unit: {unit}")


def to_pu_impedance(value_ohm: float, base: PerUnitBase) -> float:
    if value_ohm < 0:
        raise ValueError("impedance in ohm must be non-negative")
    return value_ohm / base.impedance_base_ohm


def from_pu_impedance(value_pu: float, base: PerUnitBase) -> float:
    if value_pu < 0:
        raise ValueError("per-unit impedance must be non-negative")
    return value_pu * base.impedance_base_ohm


def to_pu_voltage(value_kv: float, base: PerUnitBase) -> float:
    if value_kv <= 0:
        raise ValueError("voltage in kV must be positive")
    return value_kv / base.voltage_base_kv


def from_pu_voltage(value_pu: float, base: PerUnitBase) -> float:
    if value_pu <= 0:
        raise ValueError("per-unit voltage must be positive")
    return value_pu * base.voltage_base_kv


def assert_pu_voltage(value_pu: float) -> None:
    if value_pu <= 0:
        raise ValueError("per-unit voltage must be positive")
    if value_pu > 2.0:
        raise ValueError("voltage appears not to be in p.u.; expected a value near 1.0")

