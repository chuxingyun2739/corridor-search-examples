from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import BranchPU, LoadPU
from .per_unit import assert_pu_voltage


@dataclass(frozen=True)
class BranchPowerPU:
    p_pu: float
    q_pu: float


@dataclass(frozen=True)
class BranchElectricalResult:
    current_pu: float
    active_loss_pu: float
    reactive_loss_pu: float
    voltage_drop_pu: float
    arrival_voltage_pu: float
    apparent_power_pu: float
    capacity_violation: bool


def fixed_transfer_power(p_transfer_pu: float, q_transfer_pu: float) -> BranchPowerPU:
    return BranchPowerPU(p_transfer_pu, q_transfer_pu)


def downstream_accumulated_load(path: List[int], loads: Dict[int, LoadPU]) -> Dict[Tuple[int, int], BranchPowerPU]:
    powers: Dict[Tuple[int, int], BranchPowerPU] = {}
    p_down = 0.0
    q_down = 0.0
    downstream: Dict[int, LoadPU] = {}
    for node in reversed(path[1:]):
        load = loads.get(node, LoadPU())
        p_down += load.p_pu
        q_down += load.q_pu
        downstream[node] = LoadPU(p_down, q_down)
    for u, v in zip(path, path[1:]):
        load = downstream.get(v, LoadPU())
        powers[(u, v)] = BranchPowerPU(load.p_pu, load.q_pu)
    return powers


def evaluate_branch_pu(
    branch: BranchPU,
    sending_voltage_pu: float,
    branch_power: BranchPowerPU,
) -> BranchElectricalResult:
    assert_pu_voltage(sending_voltage_pu)
    if abs(branch_power.p_pu) > 10 or abs(branch_power.q_pu) > 10:
        raise ValueError("branch power appears not to be in p.u.")
    current_pu = abs(complex(branch_power.p_pu, -branch_power.q_pu) / sending_voltage_pu)
    active_loss_pu = branch.r_pu * current_pu**2
    reactive_loss_pu = branch.x_pu * current_pu**2
    voltage_drop_pu = (branch.r_pu * branch_power.p_pu + branch.x_pu * branch_power.q_pu) / sending_voltage_pu
    arrival_voltage_pu = sending_voltage_pu - voltage_drop_pu
    apparent_power_pu = abs(complex(branch_power.p_pu, branch_power.q_pu))
    capacity_violation = branch.rate_pu is not None and apparent_power_pu > branch.rate_pu + 1e-12
    if current_pu < -1e-12 or active_loss_pu < -1e-12 or reactive_loss_pu < -1e-12:
        raise ValueError("current and losses must be non-negative")
    return BranchElectricalResult(
        current_pu=current_pu,
        active_loss_pu=active_loss_pu,
        reactive_loss_pu=reactive_loss_pu,
        voltage_drop_pu=voltage_drop_pu,
        arrival_voltage_pu=arrival_voltage_pu,
        apparent_power_pu=apparent_power_pu,
        capacity_violation=capacity_violation,
    )

