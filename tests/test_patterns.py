"""Differential checks of exact lane reduction against the full MILP.

Supplying scipy.optimize.milp explicitly bypasses the reduction. Small seeded
instances keep both formulations provably solved with a zero requested gap.
Alternative optima may allocate differently, so compare audited objectives.
"""

from copy import deepcopy
from random import Random

import pytest
from scipy.optimize import milp

from backend.optimizer import solve
from backend.schemas import Scenario
from backend.validation import validate_result


def seeded_payload(seed):
    rng = Random(7300 + seed)
    customers = []
    for j in range(1 + seed // 3):
        customers.append({
            "id": f"C{j}", "name": f"Customer {j}", "population": 100,
            "lat": 37 + rng.uniform(-0.12, 0.12),
            "lon": 127 + rng.uniform(-0.12, 0.12),
            "demand": {
                "large": rng.randint(1, 7), "small": rng.randint(0, 12),
                "premium": 0 if seed % 3 == 0 else rng.randint(1, 8),
            },
        })
    facilities = [{
        "id": f"F{i}", "name": f"Facility {i}",
        "lat": 37 + rng.uniform(-0.12, 0.12),
        "lon": 127 + rng.uniform(-0.12, 0.12),
        "fixed_cost": rng.randint(4, 16) * 10_000,
        "handling_cost": rng.randint(0, 20) * 100,
        "capacity_cbm": 100, "enabled": True,
    } for i in range(1 + seed % 3)]
    vehicles = [{
        "id": f"V{capacity}", "name": f"Vehicle {capacity}",
        "capacity_cbm": capacity,
        "fixed_cost": rng.randint(2, 20) * 1_000,
        "cost_per_km": rng.randint(1, 20) * 100,
        "enabled": True, "max_trips": None,
    } for capacity in (1, 3, 6)]
    constraints = []
    if seed in (1, 2, 4, 5, 7):
        constraints.append({
            "id": "premium-radius", "type": "premium_distance",
            "enabled": True, "value": {1: 12, 2: 8, 4: 0.01, 5: 25, 7: 20}[seed],
        })
    if seed == 5:
        constraints.append({
            "id": "blocked-arc", "type": "forbid_assignment", "enabled": True,
            "customer_id": "C0", "facility_id": "F0",
        })
    return {
        "name": f"Exact reduction differential seed {seed}",
        "customers": customers, "facilities": facilities, "vehicles": vehicles,
        "parameters": {
            "demand_multiplier": (1, 0.8, 1.5)[seed % 3],
            "fixed_cost_weight": 1, "transport_cost_weight": 1,
            "unmet_penalty": rng.randint(1, 20) * 10_000,
            "inbound_cost_per_unit": 100, "allow_unmet": seed in (2, 3, 5, 7),
            "separate_premium": seed % 2 == 0, "time_limit": 10,
            "mip_rel_gap": 0,
            "periods": [{
                "name": "Day", "demand_multiplier": (0.5, 1, 1.25, 2)[seed % 4],
                "days": 1,
            }],
        },
        "constraints": constraints,
    }


def was_reduced(result):
    return any("exact lane DP reduction" in message for message in result["diagnostics"])


def compare_to_full(payload, expect_reduction=True):
    scenario = Scenario.model_validate(payload)
    automatic = solve(scenario)
    full = solve(scenario, solver=milp)
    assert was_reduced(automatic) is expect_reduction, automatic["diagnostics"]
    assert not was_reduced(full), full["diagnostics"]
    assert automatic["status"] == full["status"], (automatic, full)
    assert full["status"] in ("optimal", "infeasible"), full
    if full["status"] == "optimal":
        assert automatic["validation"]["passed"], automatic["validation"]
        assert full["validation"]["passed"], full["validation"]
        assert validate_result(scenario, automatic)["passed"]
        assert validate_result(scenario, full)["passed"]
        assert automatic["objective"] == pytest.approx(full["objective"], rel=1e-9, abs=0.05)
        assert automatic["mip_gap"] in (None, 0)
        assert full["mip_gap"] in (None, 0)
    else:
        assert automatic["objective"] is None
        assert automatic["periods"] == []
    return automatic, full


@pytest.mark.parametrize("seed", range(8))
def test_seeded_small_instances_match_full_integer_model(seed):
    compare_to_full(seeded_payload(seed))


@pytest.mark.parametrize("allow_unmet", [True, False])
def test_handling_above_penalty_preserves_optional_and_required_service(allow_unmet):
    payload = seeded_payload(0)
    payload["customers"][0]["demand"] = {"large": 2, "small": 4, "premium": 3}
    payload["facilities"][0].update(handling_cost=300_000, fixed_cost=5_000)
    payload["parameters"].update(
        demand_multiplier=1, unmet_penalty=200_000, allow_unmet=allow_unmet,
        periods=[{"name": "Day", "demand_multiplier": 1, "days": 1}],
    )
    result, _ = compare_to_full(payload)
    assignment = result["periods"][0]["assignments"][0]
    if allow_unmet:
        assert result["open_facilities"] == []
        assert assignment["quantities"] == {"large": 0, "small": 0, "premium": 0}
        assert result["objective"] == pytest.approx(9 * 200_000)
    else:
        assert result["open_facilities"] == ["F0"]
        assert assignment["quantities"] == payload["customers"][0]["demand"]
        assert assignment["unmet"] == {"large": 0, "small": 0, "premium": 0}


def test_three_period_opening_is_shared_when_myopic_optima_would_differ():
    payload = seeded_payload(0)
    payload["customers"][0]["demand"] = {"large": 1, "small": 0, "premium": 0}
    payload["facilities"][0].update(id="A", fixed_cost=20_000, handling_cost=0)
    other = deepcopy(payload["facilities"][0])
    other.update(id="B", name="Low fixed high handling", fixed_cost=1_000, handling_cost=5_000)
    payload["facilities"].append(other)
    payload["vehicles"] = [{
        "id": "V20", "name": "Vehicle 20", "capacity_cbm": 20,
        "fixed_cost": 10_000, "cost_per_km": 0, "enabled": True,
    }]
    payload["parameters"].update(
        demand_multiplier=1, inbound_cost_per_unit=0, allow_unmet=False,
        periods=[
            {"name": "Year 1", "demand_multiplier": 1, "days": 365},
            {"name": "Year 2", "demand_multiplier": 5, "days": 365},
            {"name": "Year 3", "demand_multiplier": 10, "days": 365},
        ],
    )
    result, _ = compare_to_full(payload)
    # B is cheapest for year 1 alone (16,000 versus 30,000 per day).
    # With a single three-year opening decision, A costs 30,000 every day;
    # B would cost 16,000 + 36,000 + 61,000 across the three representative days.
    assert result["open_facilities"] == ["A"]
    assert result["objective"] == pytest.approx(30_000 * 365 * 3)
    for row, demand in zip(result["periods"], (1, 5, 10)):
        assert row["costs"]["fixed"] == pytest.approx(20_000)
        assert row["assignments"][0]["facility_id"] == "A"
        assert row["assignments"][0]["quantities"]["large"] == demand


@pytest.mark.parametrize("coupled_resource", ["capacity", "min_fulfillment", "budget", "max_trips", "vehicle_limit"])
def test_cross_lane_resource_constraints_use_the_full_model(coupled_resource):
    payload = seeded_payload(2)
    payload["parameters"].update(demand_multiplier=1, allow_unmet=True)
    if coupled_resource == "vehicle_limit":
        payload["vehicles"][0]["max_trips"] = 1
    else:
        values = {"capacity": 2, "min_fulfillment": 0.5, "budget": 500_000, "max_trips": 2}
        payload["constraints"].append({
            "id": "coupled-limit", "type": coupled_resource,
            "enabled": True, "value": values[coupled_resource],
        })
    result, _ = compare_to_full(payload, expect_reduction=False)
    assert any("MILP" in message for message in result["diagnostics"])


def test_disabled_coupled_constraint_keeps_reduction_enabled():
    payload = seeded_payload(2)
    payload["constraints"].append({
        "id": "inactive-capacity", "type": "capacity", "enabled": False, "value": 1,
    })
    compare_to_full(payload)
