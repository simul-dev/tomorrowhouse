"""Independent, small exact cases for the public optimization contract.

The expected answers below use hand arithmetic or enumerate integer vehicle
combinations; they do not reuse the engine's objective/model construction.
"""

from copy import deepcopy
from itertools import product
from math import ceil, pi

import numpy as np
import pytest
from scipy.optimize import milp

from backend.optimizer import solve
from backend.schemas import Scenario
from backend.validation import validate_result


PRODUCTS = ("large", "small", "premium")


def base_payload():
    return {
        "name": "Independent exact case",
        "customers": [
            {
                "id": "C1", "name": "Customer 1", "population": 1,
                "lat": 37.0, "lon": 127.0,
                "demand": {"large": 8, "small": 0, "premium": 0},
            }
        ],
        "facilities": [
            {
                "id": "A", "name": "Facility A", "lat": 37.0,
                "lon": 127.0, "fixed_cost": 10_000,
                "handling_cost": 20, "capacity_cbm": 100, "enabled": True,
            }
        ],
        "vehicles": [
            {
                "id": "v6", "name": "Six CBM", "capacity_cbm": 6,
                "fixed_cost": 60_000, "cost_per_km": 1_000,
                "enabled": True, "max_trips": None,
            },
            {
                "id": "v10", "name": "Ten CBM", "capacity_cbm": 10,
                "fixed_cost": 95_000, "cost_per_km": 1_000,
                "enabled": True, "max_trips": None,
            },
        ],
        "parameters": {
            "demand_multiplier": 1, "fixed_cost_weight": 1,
            "transport_cost_weight": 1, "unmet_penalty": 200_000,
            "inbound_cost_per_unit": 30, "allow_unmet": False,
            "separate_premium": True, "time_limit": 10,
            "mip_rel_gap": 0,
            "periods": [{"name": "Day", "demand_multiplier": 1, "days": 1}],
        },
        "constraints": [],
    }


def constraint(kind, value=None, **scope):
    item = {"id": f"{kind}-{len(scope)}", "type": kind, "enabled": True}
    if value is not None:
        item["value"] = value
    item.update(scope)
    return item


def add_facility(payload, facility_id="B", **changes):
    facility = deepcopy(payload["facilities"][0])
    facility.update(id=facility_id, name=f"Facility {facility_id}", lat=37.01)
    facility.update(changes)
    payload["facilities"].append(facility)
    return facility


def model(payload):
    return Scenario.model_validate(payload)


def as_dict(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


def solved(payload):
    scenario = model(payload)
    result = as_dict(solve(scenario))
    assert result["status"] == "optimal", result
    assert result["validation"]["passed"], result["validation"]
    independently_checked = as_dict(validate_result(scenario, result))
    assert independently_checked["passed"], independently_checked
    return result


def period(result):
    return result["periods"][0]


def assignment(result, customer_id="C1", period_index=0):
    rows = [
        row for row in result["periods"][period_index]["assignments"]
        if row["customer_id"] == customer_id
    ]
    assert len(rows) == 1, "Every customer must have exactly one output row."
    return rows[0]


def assert_infeasible(payload):
    result = as_dict(solve(model(payload)))
    assert result["status"] == "infeasible", result
    assert result.get("diagnostics") or result.get("message")


def test_hand_calculated_weighted_cost_and_unit_handling():
    payload = base_payload()
    payload["customers"][0]["demand"] = {"large": 3, "small": 10, "premium": 0}
    payload["parameters"].update(fixed_cost_weight=2, transport_cost_weight=1.5)
    result = solved(payload)
    costs = period(result)["costs"]
    # Five CBM in one six-CBM trip, but thirteen separately handled articles.
    assert costs["fixed"] == pytest.approx(20_000)
    assert costs["handling"] == pytest.approx(13 * 20)
    assert costs["inbound"] == pytest.approx(13 * 30)
    assert costs["transport_normal"] == pytest.approx(1.5 * 60_000)
    assert costs["transport_premium"] == 0
    assert costs["penalty"] == 0
    assert result["objective"] == pytest.approx(110_650)
    assert costs["total"] == pytest.approx(sum(
        costs[key] for key in (
            "fixed", "handling", "inbound", "transport_normal",
            "transport_premium", "penalty",
        )
    ))


def test_integer_vehicle_mix_matches_independent_complete_enumeration():
    payload = base_payload()
    payload["customers"][0]["demand"]["large"] = 16
    result = solved(payload)
    bounds = range(ceil(16 / 6) + 1)
    feasible = [
        (60_000 * n6 + 95_000 * n10, n6, n10)
        for n6, n10 in product(bounds, repeat=2)
        if 6 * n6 + 10 * n10 >= 16
    ]
    expected, n6, n10 = min(feasible)
    assert (n6, n10) == (1, 1)
    assert period(result)["costs"]["transport_normal"] == pytest.approx(expected)
    assert result["objective"] == pytest.approx(10_000 + 16 * 50 + expected)
    actual = {row["vehicle_id"]: row["trips"] for row in period(result)["trips"]}
    assert actual == {"v6": 1, "v10": 1}
    assert sum(row["load_cbm"] for row in period(result)["trips"]) == pytest.approx(16)


def test_premium_separation_requires_additional_trip_and_mixed_cost_is_normal():
    payload = base_payload()
    payload["customers"][0]["demand"] = {"large": 1, "small": 0, "premium": 1}
    separated = solved(payload)
    payload["parameters"]["separate_premium"] = False
    mixed = solved(payload)
    assert {row["group"] for row in period(separated)["trips"]} == {"normal", "premium"}
    assert sum(row["trips"] for row in period(separated)["trips"]) == 2
    assert sum(row["trips"] for row in period(mixed)["trips"]) == 1
    assert separated["objective"] - mixed["objective"] == pytest.approx(60_000)
    assert period(mixed)["costs"]["transport_normal"] == pytest.approx(60_000)
    assert period(mixed)["costs"]["transport_premium"] == 0


def test_premium_radius_allows_general_delivery_and_partial_product_unmet():
    payload = base_payload()
    payload["facilities"][0]["lat"] = 37.5
    payload["customers"][0]["demand"] = {"large": 1, "small": 0, "premium": 2}
    payload["parameters"]["allow_unmet"] = True
    payload["constraints"] = [constraint("premium_distance", 30)]
    result = solved(payload)
    row = assignment(result)
    assert row["distance_km"] > 30
    assert row["quantities"] == {"large": 1, "small": 0, "premium": 0}
    assert row["unmet"] == {"large": 0, "small": 0, "premium": 2}
    assert period(result)["costs"]["penalty"] == pytest.approx(400_000)
    assert all(row["group"] == "normal" for row in period(result)["trips"])
    # The hypothetical mixed fleet must retain the premium-specific radius.
    payload["parameters"]["separate_premium"] = False
    assert assignment(solved(payload))["unmet"]["premium"] == 2


def test_single_dc_couples_general_and_premium_even_when_split_is_cheaper():
    payload = base_payload()
    payload["customers"][0]["demand"] = {"large": 1, "small": 0, "premium": 1}
    payload["facilities"][0]["handling_cost"] = 100_000
    add_facility(payload, lat=37.4, handling_cost=0)
    payload["constraints"] = [
        constraint("premium_distance", 10),
        constraint("force_open", facility_id="A", id="open-a"),
        constraint("force_open", facility_id="B", id="open-b"),
    ]
    result = solved(payload)
    assert set(result["open_facilities"]) == {"A", "B"}
    assert assignment(result)["facility_id"] == "A"
    assert {row["facility_id"] for row in period(result)["trips"]} == {"A"}
    assert assignment(result)["unmet"] == dict.fromkeys(PRODUCTS, 0)


def test_closed_facility_has_no_assignments_or_trips():
    payload = base_payload()
    add_facility(payload, fixed_cost=100_000_000)
    result = solved(payload)
    assert result["open_facilities"] == ["A"]
    assert assignment(result)["facility_id"] == "A"
    assert all(row["facility_id"] in result["open_facilities"] for row in period(result)["trips"])


def test_capacity_constraint_toggle_changes_feasible_product_quantities():
    payload = base_payload()
    payload["parameters"]["allow_unmet"] = True
    payload["facilities"][0]["capacity_cbm"] = 4
    payload["constraints"] = [constraint("capacity", enabled=False)]
    unlimited = solved(payload)
    assert assignment(unlimited)["quantities"]["large"] == 8
    payload["constraints"][0]["enabled"] = True
    limited = solved(payload)
    assert assignment(limited)["quantities"]["large"] == 4
    assert assignment(limited)["unmet"]["large"] == 4
    assert period(limited)["facilities"][0]["load_cbm"] == pytest.approx(4)


def test_force_and_forbid_same_facility_is_infeasible():
    payload = base_payload()
    payload["parameters"]["allow_unmet"] = True
    payload["constraints"] = [
        constraint("force_open", facility_id="A"),
        constraint("forbid_open", facility_id="A"),
    ]
    assert_infeasible(payload)


def test_allow_assignment_rows_form_union_and_exclude_unlisted_cheapest_dc():
    payload = base_payload()
    payload["facilities"][0]["fixed_cost"] = 500_000
    add_facility(payload, "B", fixed_cost=10_000)
    add_facility(payload, "C", lat=37.0, fixed_cost=1)
    payload["constraints"] = [
        constraint("allow_assignment", customer_id="C1", facility_id="A", id="allow-a"),
        constraint("allow_assignment", customer_id="C1", facility_id="B", id="allow-b"),
    ]
    result = solved(payload)
    assert assignment(result)["facility_id"] == "B"
    assert result["open_facilities"] == ["B"]


def test_forbid_assignment_removes_the_normally_best_arc():
    payload = base_payload()
    add_facility(payload)
    payload["constraints"] = [constraint("forbid_assignment", customer_id="C1", facility_id="A")]
    assert assignment(solved(payload))["facility_id"] == "B"


def test_vehicle_trip_limit_causes_exact_partial_unmet():
    payload = base_payload()
    payload["vehicles"][1]["enabled"] = False
    payload["parameters"]["allow_unmet"] = True
    payload["constraints"] = [constraint("max_trips", 1, vehicle_id="v6")]
    result = solved(payload)
    assert assignment(result)["quantities"]["large"] == 6
    assert assignment(result)["unmet"]["large"] == 2
    assert sum(row["trips"] for row in period(result)["trips"]) == 1


def test_fulfillment_floor_detects_insufficient_vehicle_availability():
    payload = base_payload()
    payload["vehicles"][1]["enabled"] = False
    payload["vehicles"][0]["max_trips"] = 1
    payload["parameters"]["allow_unmet"] = True
    payload["constraints"] = [constraint("min_fulfillment", 0.9)]
    assert_infeasible(payload)


def test_daily_budget_is_applied_to_full_cost_including_inbound():
    payload = base_payload()
    # Exact optimum is 10,000 + 8*(20+30) + 95,000 = 105,400 won.
    payload["constraints"] = [constraint("budget", 106_000)]
    assert solved(payload)["objective"] == pytest.approx(105_400)
    payload["constraints"][0]["value"] = 100_000
    assert_infeasible(payload)


def test_minimum_and_maximum_open_dc_counts_apply_even_to_unused_facility():
    payload = base_payload()
    add_facility(payload)
    payload["constraints"] = [constraint("min_dcs", 2), constraint("max_dcs", 2)]
    result = solved(payload)
    assert set(result["open_facilities"]) == {"A", "B"}
    assert period(result)["costs"]["fixed"] == pytest.approx(20_000)
    payload["constraints"][1]["value"] = 1
    assert_infeasible(payload)


def test_multiperiod_shares_opening_multiplies_growth_and_weights_daily_cost():
    payload = base_payload()
    payload["customers"][0]["demand"]["large"] = 1
    add_facility(payload, fixed_cost=100_000)
    payload["parameters"].update(
        demand_multiplier=2,
        periods=[
            {"name": "Year 1", "demand_multiplier": 1, "days": 2},
            {"name": "Year 2", "demand_multiplier": 1.25, "days": 3},
        ],
    )
    result = solved(payload)
    assert result["open_facilities"] == ["A"]
    assert assignment(result, period_index=0)["quantities"]["large"] == 2
    # 1 * 2 * 1.25 = 2.5, rounded up, rather than banker's rounding to 2.
    assert assignment(result, period_index=1)["quantities"]["large"] == 3
    for row in result["periods"]:
        assert row["costs"]["fixed"] == pytest.approx(10_000)
        assert row["kpis"]["open_dcs"] == 1
        assert all(a["facility_id"] in result["open_facilities"] for a in row["assignments"])
    assert result["objective"] == pytest.approx(2 * 70_100 + 3 * 70_150)
    assert result["objective"] == pytest.approx(sum(
        row["days"] * row["costs"]["total"] for row in result["periods"]
    ))


def test_moving_dc_recalculates_one_way_cost_and_round_trip_distance():
    payload = base_payload()
    payload["customers"][0]["demand"]["large"] = 5
    before = solved(payload)
    payload["facilities"][0]["lat"] = 37.1
    after = solved(payload)
    expected_km = 6371.0088 * pi / 180 * 0.1
    assert assignment(before)["distance_km"] == pytest.approx(0)
    assert assignment(after)["distance_km"] == pytest.approx(expected_km, rel=1e-8)
    assert after["objective"] - before["objective"] == pytest.approx(1_000 * expected_km)
    assert period(after)["kpis"]["total_distance_km"] == pytest.approx(2 * expected_km)
    assert period(after)["kpis"]["average_distance_km"] == pytest.approx(expected_km)
    assert period(after)["kpis"]["max_distance_km"] == pytest.approx(expected_km)


@pytest.mark.parametrize("allow_unmet", [True, False])
def test_all_vehicles_disabled_has_defined_behavior(allow_unmet):
    payload = base_payload()
    payload["parameters"]["allow_unmet"] = allow_unmet
    for vehicle in payload["vehicles"]:
        vehicle["enabled"] = False
    if not allow_unmet:
        assert_infeasible(payload)
        return
    result = solved(payload)
    assert result["open_facilities"] == []
    assert period(result)["trips"] == []
    assert assignment(result)["facility_id"] is None
    assert assignment(result)["quantities"] == dict.fromkeys(PRODUCTS, 0)
    assert assignment(result)["unmet"]["large"] == 8
    assert result["objective"] == pytest.approx(8 * 200_000)


def test_general_maximum_distance_restricts_all_products():
    payload = base_payload()
    payload["facilities"][0]["lat"] = 37.5
    payload["customers"][0]["demand"] = {"large": 1, "small": 1, "premium": 1}
    payload["parameters"]["allow_unmet"] = True
    payload["constraints"] = [constraint("max_distance", 30)]
    result = solved(payload)
    assert assignment(result)["quantities"] == dict.fromkeys(PRODUCTS, 0)
    assert assignment(result)["unmet"] == dict.fromkeys(PRODUCTS, 1)


def test_customer_scoped_premium_radius_does_not_restrict_other_customers():
    payload = base_payload()
    payload["facilities"][0]["lat"] = 37.5
    payload["customers"][0]["demand"] = {"large": 1, "small": 0, "premium": 1}
    other = deepcopy(payload["customers"][0])
    other.update(id="C2", name="Customer 2", lat=37.01)
    payload["customers"].append(other)
    payload["parameters"]["allow_unmet"] = True
    payload["constraints"] = [constraint("premium_distance", 30, customer_id="C1")]
    result = solved(payload)
    assert assignment(result, "C1")["unmet"]["premium"] == 1
    assert assignment(result, "C2")["quantities"]["premium"] == 1
    assert assignment(result, "C1")["quantities"]["large"] == 1


def test_independent_validator_rejects_quantity_capacity_opening_and_cost_tampering():
    payload = base_payload()
    payload["customers"][0]["demand"] = {"large": 2, "small": 0, "premium": 2}
    scenario = model(payload)
    original = solved(payload)
    cases = {}

    changed = deepcopy(original)
    changed["periods"][0]["assignments"][0]["quantities"]["large"] += 1
    cases["demand conservation"] = changed

    changed = deepcopy(original)
    changed["periods"][0]["trips"][0]["trips"] = 0
    cases["insufficient vehicle capacity"] = changed

    changed = deepcopy(original)
    changed["open_facilities"] = []
    cases["assignment to closed facility"] = changed

    changed = deepcopy(original)
    changed["objective"] += 10_000
    cases["objective total"] = changed

    changed = deepcopy(original)
    changed["periods"][0]["costs"]["handling"] += 10_000
    cases["cost component"] = changed

    changed = deepcopy(original)
    premium_row = next(t for t in changed["periods"][0]["trips"] if t["group"] == "premium")
    premium_row["group"] = "normal"
    cases["premium fleet separation"] = changed

    for label, changed in cases.items():
        checked = as_dict(validate_result(scenario, changed))
        assert not checked["passed"], f"Validator accepted tampering: {label}"
        assert checked["errors"], f"Validator omitted diagnostic: {label}"


def test_solver_time_limit_without_incumbent_returns_no_solution():
    def limit_without_incumbent(**_):
        return {"status": 1, "x": None, "message": "Time limit without incumbent"}

    result = solve(model(base_payload()), solver=limit_without_incumbent)
    assert result["status"] == "no_solution"
    assert result["objective"] is None
    assert result["periods"] == []
    assert not result["validation"]["passed"]


def test_solver_fractional_relaxation_is_not_exported_as_integer_incumbent():
    def fractional_relaxation(**kwargs):
        return {"status": 1, "x": np.full(len(kwargs["c"]), 0.5),
                "message": "Only fractional relaxation available"}

    result = solve(model(base_payload()), solver=fractional_relaxation)
    assert result["status"] == "no_solution"
    assert result["objective"] is None
    assert result["open_facilities"] == []
    assert result["periods"] == []


def test_solver_integer_but_infeasible_incumbent_is_rejected_by_independent_audit():
    def invalid_integer_incumbent(**kwargs):
        # Within every variable's bounds and integral, but violates demand.
        return {"status": 0, "x": np.zeros(len(kwargs["c"])),
                "message": "Incorrect solver success", "mip_gap": 0}

    result = solve(model(base_payload()), solver=invalid_integer_incumbent)
    assert result["status"] == "error"
    assert result["objective"] is None
    assert result["periods"] == []
    assert not result["validation"]["passed"]
    assert result["validation"]["errors"]


def test_solver_time_limit_with_real_feasible_incumbent_keeps_audited_solution():
    def limited_real_solver(**kwargs):
        answer = milp(**kwargs)
        assert answer.status == 0
        assert answer.x is not None
        answer.status = 1
        answer.message = "Injected time limit after obtaining a real incumbent"
        answer.mip_gap = 0.125
        return answer

    scenario = model(base_payload())
    result = solve(scenario, solver=limited_real_solver)
    assert result["status"] == "feasible_limit"
    assert result["mip_gap"] == pytest.approx(0.125)
    assert result["objective"] == pytest.approx(105_400)
    assert result["validation"]["passed"]
    assert validate_result(scenario, result)["passed"]


def test_solver_failure_status_is_error_even_if_an_incumbent_is_attached():
    def failed_solver(**kwargs):
        answer = milp(**kwargs)
        assert answer.x is not None
        answer.status = 4
        answer.message = "Injected numerical failure"
        return answer

    result = solve(model(base_payload()), solver=failed_solver)
    assert result["status"] == "error"
    assert result["objective"] is None
    assert result["periods"] == []
    assert not result["validation"]["passed"]


def test_custom_distance_provider_is_shared_by_cost_and_independent_validation():
    calls = []

    def custom_road_distance(lat1, lon1, lat2, lon2):
        calls.append((lat1, lon1, lat2, lon2))
        return 7.5

    scenario = model(base_payload())
    result = solve(scenario, distance_provider=custom_road_distance)
    assert result["status"] == "optimal", result
    assert result["validation"]["passed"], result["validation"]
    assert len(calls) >= 2, "Construction and independent audit must both use the provider."
    assert assignment(result)["distance_km"] == pytest.approx(7.5)
    assert result["objective"] == pytest.approx(105_400 + 7_500)
    assert period(result)["kpis"]["total_distance_km"] == pytest.approx(15)
    assert validate_result(scenario, result, distance_provider=custom_road_distance)["passed"]
    # Coordinates coincide: checking road-distance output with Haversine must fail.
    assert not validate_result(scenario, result)["passed"]


def custom(terms, operator, rhs, rule_id="custom-rule"):
    return {"id": rule_id, "type": "custom", "enabled": True,
            "operator": operator, "rhs": rhs, "terms": terms}


def term(metric, coefficient=1, **scope):
    return {"metric": metric, "coefficient": coefficient, **scope}


def test_custom_open_count_reproduces_the_min_dcs_template_exactly():
    """The custom builder and the dedicated template must agree, although only
    the template keeps the exact lane reduction active."""
    payload = base_payload()
    add_facility(payload)
    payload["constraints"] = [constraint("min_dcs", 2)]
    template_result = solved(payload)
    payload["constraints"] = [custom([term("open")], ">=", 2)]
    custom_result = solved(payload)
    assert set(custom_result["open_facilities"]) == {"A", "B"}
    assert custom_result["objective"] == pytest.approx(template_result["objective"])
    assert custom_result["objective"] == pytest.approx(115_400)


def test_custom_term_coefficients_price_vehicles_against_a_shared_allowance():
    # Weighted trip budget: a 10 CBM trip costs 5 of the 4 available units, so
    # the 8 CBM demand must move on two 6 CBM trips instead of one 10 CBM trip.
    payload = base_payload()
    payload["constraints"] = [custom(
        [term("trips", 5, vehicle_id="v10"), term("trips", 1, vehicle_id="v6")], "<=", 4)]
    result = solved(payload)
    assert period(result)["kpis"]["trips_by_vehicle"] == {"v6": 2, "v10": 0}
    assert result["objective"] == pytest.approx(10_000 + 400 + 2 * 60_000)


def test_custom_volume_bound_is_infeasible_below_mandatory_demand():
    payload = base_payload()
    payload["constraints"] = [custom([term("cbm")], ">=", 8)]
    assert solved(payload)["objective"] == pytest.approx(105_400)
    payload["constraints"] = [custom([term("cbm")], "<=", 5)]
    assert_infeasible(payload)


def test_custom_unmet_bound_applies_per_product_filter():
    payload = base_payload()
    payload["parameters"]["allow_unmet"] = True
    payload["customers"][0]["demand"] = {"large": 8, "small": 0, "premium": 0}
    # A single large unit costs 20+30 to serve and 200,000 to abandon, so the
    # unconstrained optimum ships everything; the equality forces two unmet.
    payload["constraints"] = [custom([term("unmet", product="large")], "==", 2)]
    result = solved(payload)
    assert assignment(result)["unmet"] == {"large": 2, "small": 0, "premium": 0}
    assert period(result)["costs"]["penalty"] == pytest.approx(400_000)


def test_custom_rule_is_audited_independently_of_the_solver():
    payload = base_payload()
    clean = solved(payload)
    assert period(clean)["kpis"]["trips_by_vehicle"] == {"v6": 0, "v10": 1}
    # The same result document, re-audited against a scenario whose custom rule
    # it violates, must be rejected without re-running the solver.
    payload["constraints"] = [custom([term("trips", vehicle_id="v10")], "<=", 0)]
    audit = as_dict(validate_result(model(payload), clean))
    assert not audit["passed"]
    assert any("custom-rule" in message for message in audit["errors"]), audit


def test_custom_zero_and_negative_right_hand_sides_stay_linear():
    payload = base_payload()
    payload["constraints"] = [custom([term("trips", -1)], ">=", -2)]
    assert solved(payload)["objective"] == pytest.approx(105_400)
    payload["constraints"] = [custom([term("trips", -1)], ">=", 0)]
    assert_infeasible(payload)
