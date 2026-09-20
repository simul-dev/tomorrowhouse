"""Sparse, integer, multi-period facility-location model, independent of the UI.

Money is scaled to million KRW only at the solver boundary. Quantities and
round trips are integers; the shared facility decisions are binary. The public
result is reconstructed in KRW and independently audited before release.
"""
from __future__ import annotations

from collections import defaultdict
from math import ceil, floor, isfinite
from time import perf_counter
from typing import Callable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .distance import DistanceProvider, haversine_km
from .patterns import build_pattern_reduction
from .schemas import PRODUCTS, VOLUMES, Scenario
from .validation import validate_result

MONEY_SCALE = 1_000_000.0
DISTANCE_EPS = 1e-6


class _Model:
    """Small sparse model builder; variable keys have explicit business indices."""

    def __init__(self):
        self.index: dict[tuple, int] = {}
        self.cost: list[float] = []
        self.upper: list[float] = []
        self.rows: list[int] = []
        self.cols: list[int] = []
        self.values: list[float] = []
        self.lower_rows: list[float] = []
        self.upper_rows: list[float] = []

    def variable(self, key, upper, cost=0.0):
        idx = len(self.cost)
        self.index[key] = idx
        self.cost.append(float(cost) / MONEY_SCALE)
        self.upper.append(float(upper))
        return idx

    def row(self, entries, lower=-np.inf, upper=np.inf):
        row = len(self.lower_rows)
        for col, value in entries:
            if value:
                self.rows.append(row)
                self.cols.append(col)
                self.values.append(float(value))
        self.lower_rows.append(float(lower))
        self.upper_rows.append(float(upper))

    def linear_constraint(self):
        matrix = coo_matrix(
            (self.values, (self.rows, self.cols)),
            shape=(len(self.lower_rows), len(self.cost)), dtype=float,
        ).tocsc()
        return LinearConstraint(matrix, self.lower_rows, self.upper_rows)


def _blank_result(start, status, message, constraints=(), diagnostics=()):
    return {
        "status": status, "message": message,
        "runtime_seconds": round(perf_counter() - start, 6),
        "mip_gap": None, "objective": None, "open_facilities": [],
        "periods": [],
        "validation": {"passed": False, "errors": ["실행 가능한 해가 없어 결과 검산을 수행하지 않았습니다."]},
        "diagnostics": list(diagnostics), "applied_constraints": list(constraints),
    }


def _diagnostic_hints(data, active):
    """Explanatory hints, deliberately not presented as an IIS certificate."""
    hints = []
    facilities = data["facilities"]
    available = [f for f in facilities if f["enabled"]]
    if not available:
        hints.append("활성 DC 후보가 없습니다. 출고가 필요한 정책에서는 실행 불가능할 수 있습니다.")
    if not any(v["enabled"] for v in data["vehicles"]):
        hints.append("활성 차량이 없습니다. 모든 수요를 미충족 처리할 수 있는 설정에서만 해가 가능합니다.")
    forced = {c["facility_id"] for c in active if c["type"] == "force_open"}
    forbidden = {c["facility_id"] for c in active if c["type"] == "forbid_open"}
    disabled = {f["id"] for f in facilities if not f["enabled"]}
    if forced & (forbidden | disabled):
        hints.append("동일 DC에 강제 개설과 개설 금지/비활성이 동시에 지정되어 있습니다.")
    lower = max([c["value"] for c in active if c["type"] == "min_dcs"] or [0])
    upper = min([c["value"] for c in active if c["type"] == "max_dcs"] or [len(facilities)])
    if lower > min(upper, len(available)) or len(forced) > upper:
        hints.append("최소/최대 개설 수, 강제 개설 수 또는 활성 후보 수가 충돌합니다.")
    return hints


def solve(scenario: Scenario | dict, solver: Callable | None = None,
          distance_provider: DistanceProvider | None = None) -> dict:
    """Solve a validated scenario, using a SciPy-milp-compatible callable if given.

    The solver boundary accepts ``c, integrality, bounds, constraints, options``
    and returns an object with ``status, x, message, mip_gap`` attributes. This
    permits alternate adapters and deterministic tests of time-limit behavior.
    A supplied solver receives the full formulation. The default solver uses
    exact lane-pattern reduction when there are no coupled lane constraints.
    """
    start = perf_counter()
    active = []
    diagnostics = []
    try:
        scenario = scenario if isinstance(scenario, Scenario) else Scenario.model_validate(scenario)
        data = scenario.model_dump()
        active = [c for c in data["constraints"] if c["enabled"]]
        diagnostics = _diagnostic_hints(data, active)
        distance_provider = distance_provider or haversine_km
        model, distances, demand, groups, _ = _build_model(data, active, distance_provider)
        reduction = build_pattern_reduction(data, active, model, distances, demand, groups) if solver is None else None
        solve_model = reduction.model if reduction is not None else model
        if reduction is not None:
            diagnostics.append(f"정확한 운송구간 DP 축약(exact lane DP reduction): {len(reduction.plans):,}개 운송 계획, "
                               f"변수 {len(model.cost):,} → {len(solve_model.cost):,}. 원모형과 동치입니다.")
        answer = (solver or milp)(
            c=np.asarray(solve_model.cost),
            integrality=np.ones(len(solve_model.cost), dtype=np.uint8),
            bounds=Bounds(np.zeros(len(solve_model.cost)), np.asarray(solve_model.upper)),
            constraints=solve_model.linear_constraint(),
            options={"time_limit": data["parameters"]["time_limit"],
                     "mip_rel_gap": data["parameters"]["mip_rel_gap"], "presolve": True},
        )
        read = lambda key, default=None: answer.get(key, default) if isinstance(answer, dict) else getattr(answer, key, default)
        code = read("status", 4)
        diagnostics.append(f"MILP 정수변수 {len(solve_model.cost):,}개, 선형 제약 {len(solve_model.lower_rows):,}개.")
        diagnostics.append(f"Solver: {read('message', '상태 메시지 없음')}")
        if code == 2:
            diagnostics.append("진단은 제약 충돌의 추정 힌트이며 IIS 증명이 아닙니다. 충족률·거리·차량 회차·용량·예산을 함께 확인하세요.")
            return _blank_result(start, "infeasible", "지정된 제약을 모두 만족하는 해가 없습니다.", active, diagnostics)
        raw = read("x")
        if code not in (0, 1):
            return _blank_result(start, "error", "Solver가 정상적으로 해를 반환하지 못했습니다.", active, diagnostics)
        if raw is None:
            return _blank_result(start, "no_solution", "제한 시간 내 실행 가능한 정수해를 찾지 못했습니다.", active, diagnostics)
        values = np.asarray(raw, dtype=float)
        if values.shape != (len(solve_model.cost),) or not np.all(np.isfinite(values)):
            return _blank_result(start, "error", "Solver가 유효하지 않은 해 벡터를 반환했습니다.", active, diagnostics)
        if np.max(np.abs(values - np.rint(values)), initial=0) > 1e-4:
            return _blank_result(start, "no_solution", "정수 조건을 만족하는 incumbent가 없어 결과를 반환하지 않습니다.", active, diagnostics)
        values = np.rint(values).astype(np.int64)
        if np.any(values < 0) or np.any(values > np.asarray(solve_model.upper) + 1e-6):
            return _blank_result(start, "error", "Solver 해가 변수 범위를 벗어났습니다.", active, diagnostics)
        if reduction is not None:
            values = reduction.expand(values)
        gap_raw = read("mip_gap")
        gap = float(gap_raw) if gap_raw is not None and isfinite(float(gap_raw)) else None
        if code == 0:
            message = (f"허용오차 내 최적해(optimal within tolerance), MIP gap {gap:.4%}. 정확한 전역 최적성은 미증명입니다."
                       if gap is not None and gap > 1e-8 else "선택한 후보와 수리모형에서 최적해를 찾았습니다.")
            status = "optimal"
        else:
            status = "feasible_limit"
            message = "제한 시간에 도달했습니다. 독립 검산을 통과한 실행 가능해이며 최적성은 미증명입니다."
        result = _reconstruct(data, model, values, distances, demand, groups)
        result.update(status=status, message=message, mip_gap=gap,
                      runtime_seconds=round(perf_counter() - start, 6),
                      diagnostics=diagnostics, applied_constraints=active)
        result["validation"] = validate_result(scenario, result, distance_provider=distance_provider)
        result["runtime_seconds"] = round(perf_counter() - start, 6)
        if not result["validation"]["passed"]:
            result.update(status="error", message="Solver 해의 독립 검산에 실패하여 결과를 사용할 수 없습니다.",
                          objective=None, open_facilities=[], periods=[])
        return result
    except Exception as exc:
        return _blank_result(start, "error", f"최적화 오류: {type(exc).__name__}: {exc}", active, diagnostics)


def _build_model(data, active, distance_provider):
    fs, cs, vs, par = data["facilities"], data["customers"], data["vehicles"], data["parameters"]
    periods = par["periods"]
    groups = {"normal": ("large", "small"), "premium": ("premium",)} if par["separate_premium"] else {"mixed": PRODUCTS}
    distances = {(i, j): float(distance_provider(f["lat"], f["lon"], c["lat"], c["lon"]))
                 for i, f in enumerate(fs) for j, c in enumerate(cs)}
    if any(not isfinite(d) or d < 0 for d in distances.values()):
        raise ValueError("거리 공급자는 유한한 0 이상 km를 반환해야 합니다.")
    demand = {(t, j, p): floor(c["demand"][p] * (par["demand_multiplier"] * period["demand_multiplier"]) + 0.5)
              for t, period in enumerate(periods) for j, c in enumerate(cs) for p in PRODUCTS}
    allowed = defaultdict(set)
    forbidden = set()
    for con in active:
        if con["type"] == "allow_assignment":
            allowed[con["customer_id"]].add(con["facility_id"])
        elif con["type"] == "forbid_assignment":
            forbidden.add((con["facility_id"], con["customer_id"]))
    distance_limits = [c for c in active if c["type"] in ("max_distance", "premium_distance")]
    min_capacity = min((v["capacity_cbm"] for v in vs if v["enabled"]), default=None)
    model = _Model()
    daily_cost = {t: [] for t in range(len(periods))}
    idx = model.index
    for i, f in enumerate(fs):
        cost = f["fixed_cost"] * par["fixed_cost_weight"]
        var = model.variable(("y", i), int(f["enabled"]), cost * sum(p["days"] for p in periods))
        for t in daily_cost:
            daily_cost[t].append((var, cost))
    for t, period in enumerate(periods):
        days = period["days"]
        for j, customer in enumerate(cs):
            for p in PRODUCTS:
                var = model.variable(("u", t, j, p), demand[t, j, p] if par["allow_unmet"] else 0,
                                     par["unmet_penalty"] * days)
                daily_cost[t].append((var, par["unmet_penalty"]))
        for i, f in enumerate(fs):
            for j, customer in enumerate(cs):
                permitted = (f["enabled"] and (customer["id"] not in allowed or f["id"] in allowed[customer["id"]])
                             and (f["id"], customer["id"]) not in forbidden)
                a = model.variable(("a", t, i, j), int(permitted))
                model.row([(a, 1), (idx["y", i], -1)], upper=0)
                quantities = []
                for p in PRODUCTS:
                    within_distance = all(
                        con["customer_id"] not in (None, customer["id"])
                        or (con["type"] == "premium_distance" and p != "premium")
                        or distances[i, j] <= con["value"] + DISTANCE_EPS
                        for con in distance_limits)
                    qmax = demand[t, j, p] if permitted and within_distance else 0
                    cost = f["handling_cost"] + par["inbound_cost_per_unit"]
                    q = model.variable(("q", t, i, j, p), qmax, cost * days)
                    quantities.append((q, -1))
                    daily_cost[t].append((q, cost))
                    model.row([(q, 1), (a, -demand[t, j, p])], upper=0)
                model.row([(a, 1), *quantities], upper=0)
                for group, products in groups.items():
                    volume = sum(VOLUMES[p] * demand[t, j, p] for p in products)
                    max_trips = ceil((volume - 1e-9) / min_capacity) if min_capacity is not None and volume > 0 else 0
                    capacity_row = [(idx["q", t, i, j, p], VOLUMES[p]) for p in products]
                    for k, vehicle in enumerate(vs):
                        cost = par["transport_cost_weight"] * (vehicle["fixed_cost"] + vehicle["cost_per_km"] * distances[i, j])
                        n = model.variable(("n", t, i, j, group, k), max_trips if permitted and vehicle["enabled"] else 0, cost * days)
                        daily_cost[t].append((n, cost))
                        capacity_row.append((n, -vehicle["capacity_cbm"]))
                        model.row([(n, 1), (a, -max_trips)], upper=0)
                    model.row(capacity_row, upper=0)
        for j in range(len(cs)):
            model.row([(idx["a", t, i, j], 1) for i in range(len(fs))], upper=1)
            for p in PRODUCTS:
                model.row([(idx["q", t, i, j, p], 1) for i in range(len(fs))] + [(idx["u", t, j, p], 1)],
                          lower=demand[t, j, p], upper=demand[t, j, p])
        for k, vehicle in enumerate(vs):
            if vehicle["max_trips"] is not None:
                model.row([(idx["n", t, i, j, g, k], 1) for i in range(len(fs)) for j in range(len(cs)) for g in groups],
                          upper=vehicle["max_trips"])
    fi = {f["id"]: i for i, f in enumerate(fs)}
    vi = {v["id"]: k for k, v in enumerate(vs)}
    for con in active:
        kind, value = con["type"], con["value"]
        if kind in ("min_dcs", "max_dcs"):
            model.row([(idx["y", i], 1) for i in range(len(fs))],
                      lower=value if kind == "min_dcs" else -np.inf,
                      upper=value if kind == "max_dcs" else np.inf)
        elif kind in ("force_open", "forbid_open"):
            target = 1 if kind == "force_open" else 0
            model.row([(idx["y", fi[con["facility_id"]]], 1)], lower=target, upper=target)
        elif kind == "capacity":
            selected = [fi[con["facility_id"]]] if con["facility_id"] else range(len(fs))
            for t in daily_cost:
                for i in selected:
                    cap = fs[i]["capacity_cbm"] if value is None else value
                    model.row([(idx["q", t, i, j, p], VOLUMES[p]) for j in range(len(cs)) for p in PRODUCTS]
                              + [(idx["y", i], -cap)], upper=0)
        elif kind == "max_trips":
            selected = [vi[con["vehicle_id"]]] if con["vehicle_id"] else range(len(vs))
            for t in daily_cost:
                model.row([(idx["n", t, i, j, g, k], 1) for i in range(len(fs)) for j in range(len(cs))
                           for g in groups for k in selected], upper=value)
        elif kind == "min_fulfillment":
            for t in daily_cost:
                model.row([(idx["q", t, i, j, p], 1) for i in range(len(fs)) for j in range(len(cs)) for p in PRODUCTS],
                          lower=value * sum(demand[t, j, p] for j in range(len(cs)) for p in PRODUCTS))
        elif kind == "budget":
            for t in daily_cost:
                model.row([(var, cost / MONEY_SCALE) for var, cost in daily_cost[t]], upper=value / MONEY_SCALE)
    return model, distances, demand, groups, daily_cost


def _reconstruct(data, model, values, distances, demand, groups):
    fs, cs, vs, par = data["facilities"], data["customers"], data["vehicles"], data["parameters"]
    val = lambda *key: int(values[model.index[key]])
    opened = [f["id"] for i, f in enumerate(fs) if val("y", i)]
    periods = []
    for t, period in enumerate(par["periods"]):
        assignments, trips = [], []
        facility_units = defaultdict(int)
        facility_load = defaultdict(float)
        trip_counts = {v["id"]: 0 for v in vs}
        costs = {key: 0.0 for key in ("fixed", "handling", "inbound", "transport_normal", "transport_premium", "penalty")}
        costs["fixed"] = sum(f["fixed_cost"] * par["fixed_cost_weight"] for f in fs if f["id"] in opened)
        total_demand = sum(demand[t, j, p] for j in range(len(cs)) for p in PRODUCTS)
        fulfilled = 0
        weighted_distance = total_load = total_distance = maximum_distance = 0.0
        for j, customer in enumerate(cs):
            assigned = next((i for i in range(len(fs)) if val("a", t, i, j)), None)
            quantities = {p: sum(val("q", t, i, j, p) for i in range(len(fs))) for p in PRODUCTS}
            unmet = {p: val("u", t, j, p) for p in PRODUCTS}
            distance = distances[assigned, j] if assigned is not None else None
            assignments.append({"customer_id": customer["id"], "facility_id": fs[assigned]["id"] if assigned is not None else None,
                                "distance_km": distance, "quantities": quantities, "unmet": unmet})
            units = sum(quantities.values())
            load = sum(quantities[p] * VOLUMES[p] for p in PRODUCTS)
            fulfilled += units
            costs["inbound"] += units * par["inbound_cost_per_unit"]
            costs["penalty"] += sum(unmet.values()) * par["unmet_penalty"]
            if assigned is None:
                continue
            facility = fs[assigned]
            facility_units[facility["id"]] += units
            facility_load[facility["id"]] += load
            costs["handling"] += facility["handling_cost"] * units
            total_load += load
            weighted_distance += distance * load
            maximum_distance = max(maximum_distance, distance)
            for group, products in groups.items():
                remaining = sum(quantities[p] * VOLUMES[p] for p in products)
                for k, vehicle in enumerate(vs):
                    count = val("n", t, assigned, j, group, k)
                    if not count:
                        continue
                    capacity = count * vehicle["capacity_cbm"]
                    carried = min(capacity, max(0.0, remaining))
                    remaining -= carried
                    trips.append({"facility_id": facility["id"], "customer_id": customer["id"], "group": group,
                                  "vehicle_id": vehicle["id"], "trips": count,
                                  "load_cbm": round(carried, 8), "capacity_cbm": capacity})
                    trip_counts[vehicle["id"]] += count
                    costs["transport_premium" if group == "premium" else "transport_normal"] += (
                        par["transport_cost_weight"] * count * (vehicle["fixed_cost"] + vehicle["cost_per_km"] * distance))
                    total_distance += count * distance * 2
        costs["total"] = sum(costs.values())
        periods.append({
            "name": period["name"], "days": period["days"],
            "demand_multiplier": par["demand_multiplier"] * period["demand_multiplier"],
            "costs": costs,
            "kpis": {"open_dcs": len(opened), "total_demand": total_demand,
                     "fulfilled_demand": fulfilled, "fulfillment_rate": fulfilled / total_demand if total_demand else 1.0,
                     "total_trips": sum(trip_counts.values()), "total_distance_km": total_distance,
                     "average_distance_km": weighted_distance / total_load if total_load else 0.0,
                     "max_distance_km": maximum_distance, "trips_by_vehicle": trip_counts},
            "assignments": assignments, "trips": trips,
            "facilities": [{"id": f["id"], "units": facility_units[f["id"]],
                            "load_cbm": round(facility_load[f["id"]], 8),
                            "share": facility_load[f["id"]] / total_load if total_load else 0.0} for f in fs],
        })
    return {"objective": sum(period["costs"]["total"] * period["days"] for period in periods),
            "open_facilities": opened, "periods": periods}
