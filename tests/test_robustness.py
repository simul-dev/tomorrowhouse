"""Regressions for malformed JSON that previously became valid data or HTTP 500."""
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.api import app
from backend.optimizer import solve
from backend.schemas import Scenario
from backend.validation import validate_result


@pytest.fixture
def scenario():
    return Scenario.model_validate({
        "name": "JSON boundary case",
        "customers": [{"id": "C", "name": "Customer", "lat": 37, "lon": 127,
                       "demand": {"large": 1, "small": 0, "premium": 0}}],
        "facilities": [{"id": "F", "name": "Facility", "lat": 37, "lon": 127,
                        "fixed_cost": 10, "handling_cost": 2}],
        "vehicles": [{"id": "V", "name": "Vehicle", "capacity_cbm": 1,
                      "fixed_cost": 10, "cost_per_km": 0}],
        "parameters": {"inbound_cost_per_unit": 1, "unmet_penalty": 1000,
                       "mip_rel_gap": 0},
    })


@pytest.mark.parametrize("path", [
    ("customers", 0, "demand", "large"),
    ("vehicles", 0, "capacity_cbm"),
    ("facilities", 0, "fixed_cost"),
])
def test_boolean_numeric_fields_are_rejected_instead_of_coerced_to_one(scenario, path):
    payload = scenario.model_dump()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = True
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
    response = TestClient(app).post("/api/validate", json=payload)
    assert response.status_code == 422


def test_json_integer_literals_remain_valid_for_float_fields(scenario):
    # The fixture passes integer coordinates/costs into strict float fields.
    assert scenario.facilities[0].fixed_cost == 10.0
    assert scenario.customers[0].lat == 37.0
    result = solve(scenario)
    assert result["validation"]["passed"]
    assert result["objective"] == pytest.approx(23)


def test_unknown_cost_object_is_rejected_before_excel_export(scenario):
    result = solve(scenario)
    result["periods"][0]["costs"]["unexpected"] = {}
    check = validate_result(scenario, result)
    assert not check["passed"]
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/export", json={"scenario": scenario.model_dump(), "result": result})
    assert response.status_code == 422


@pytest.mark.parametrize("bad_gap", [{}, "=1+1", True, -0.1])
def test_invalid_solver_metadata_cannot_reach_excel_cells(scenario, bad_gap):
    result = solve(scenario)
    result["mip_gap"] = bad_gap
    assert not validate_result(scenario, result)["passed"]
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/export", json={"scenario": scenario.model_dump(), "result": result})
    assert response.status_code == 422


def test_unused_unknown_result_metadata_is_not_written_to_workbook(scenario):
    result = solve(scenario)
    result["unknown_metadata"] = {"payload": "=1+1"}
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/export", json={"scenario": scenario.model_dump(), "result": result})
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
