"""Independent business-rule and arithmetic audit of a public result document.

This module does not inspect the MILP matrix, solver values, or model builder.
It reconstructs demand, volumes, distances, capacity, and money from the input
and exported decisions so a feasible-looking but corrupted result is rejected.
"""
from __future__ import annotations

from collections import defaultdict
from math import ceil, floor, isclose, isfinite
from numbers import Real

from .distance import DistanceProvider, haversine_km
from .schemas import Constraint, Scenario

_PRODUCT_VOLUME = {"large": 1.0, "small": 0.2, "premium": 0.2}
_EPS = 1e-6


def _custom_lhs(terms, opened, assignment, trips, distance):
    """Recompute a custom constraint's left-hand side from the result document.

    The model builder reads the same aggregates off the MILP columns; this one
    reads them off the published assignments, unmet counts and trip rows, so a
    corrupted result cannot satisfy a user rule it actually violates.
    """
    lhs = 0.0
    for term in terms:
        metric, coefficient = term["metric"], term["coefficient"]
        f_ref, c_ref = term["facility_id"], term["customer_id"]
        v_ref, p_ref, g_ref = term["vehicle_id"], term["product"], term["group"]
        amount = 0.0
        if metric == "open":
            amount = sum(1 for fid in opened if f_ref in (None, fid))
        elif metric in ("assigned", "units", "cbm"):
            for cid, a in assignment.items():
                fid = a["facility_id"]
                if fid is None or f_ref not in (None, fid) or c_ref not in (None, cid):
                    continue
                if metric == "assigned":
                    amount += 1
                    continue
                for p, volume in _PRODUCT_VOLUME.items():
                    if p_ref in (None, p):
                        amount += a["quantities"][p] * (volume if metric == "cbm" else 1)
        elif metric == "unmet":
            for cid, a in assignment.items():
                if c_ref in (None, cid):
                    amount += sum(a["unmet"][p] for p in _PRODUCT_VOLUME if p_ref in (None, p))
        elif metric in ("trips", "distance"):
            for row in trips:
                if (f_ref in (None, row["facility_id"]) and c_ref in (None, row["customer_id"])
                        and v_ref in (None, row["vehicle_id"]) and g_ref in (None, row["group"])):
                    span = 2 * distance[row["facility_id"], row["customer_id"]] if metric == "distance" else 1
                    amount += row["trips"] * span
        lhs += coefficient * amount
    return lhs


def validate_result(scenario: Scenario | dict, result: dict,
                    distance_provider: DistanceProvider | None = None) -> dict:
    errors = []
    try:
        data = scenario.model_dump() if isinstance(scenario, Scenario) else Scenario.model_validate(scenario).model_dump()
        _audit(data, result, errors, distance_provider or haversine_km)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        errors.append(f"결과 구조/숫자 검산 오류: {type(exc).__name__}: {exc}")
    return {"passed": not errors, "errors": errors}


def _audit(data, result, errors, distance_provider):
    def check(condition, message):
        if not condition:
            errors.append(message)

    def number(value):
        return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value)

    def integer(value):
        return number(value) and value >= 0 and value == floor(value)

    def near(actual, expected, label, abs_tol=1e-5):
        check(number(actual) and isclose(actual, expected, rel_tol=1e-8, abs_tol=abs_tol),
              f"{label}: 보고값 {actual!r}, 재계산값 {expected!r}")

    if result.get("status") not in ("optimal", "feasible_limit"):
        errors.append("실행 가능한 결과 상태가 아니므로 검산할 수 없습니다.")
        return
    gap = result.get("mip_gap")
    check(gap is None or (number(gap) and gap >= 0), "MIP gap은 null 또는 유한한 0 이상 숫자여야 합니다.")
    runtime = result.get("runtime_seconds")
    check(number(runtime) and runtime >= 0, "계산시간은 유한한 0 이상 숫자여야 합니다.")
    fs = {f["id"]: f for f in data["facilities"]}
    cs = {c["id"]: c for c in data["customers"]}
    vs = {v["id"]: v for v in data["vehicles"]}
    par = data["parameters"]
    active = [c for c in data["constraints"] if c["enabled"]]
    opened_list = result["open_facilities"]
    opened = set(opened_list)
    check(len(opened_list) == len(opened), "개설 DC ID가 중복됩니다.")
    check(opened <= fs.keys(), "알 수 없는 DC가 개설 목록에 있습니다.")
    for fid in opened & fs.keys():
        check(fs[fid]["enabled"], f"비활성 DC {fid}가 개설되었습니다.")
    allowed = defaultdict(set)
    for con in active:
        kind, value = con["type"], con["value"]
        if kind == "min_dcs":
            check(len(opened) >= value, f"{con['id']}: 최소 DC 수 위반")
        elif kind == "max_dcs":
            check(len(opened) <= value, f"{con['id']}: 최대 DC 수 위반")
        elif kind == "force_open":
            check(con["facility_id"] in opened, f"{con['id']}: 강제 개설 위반")
        elif kind == "forbid_open":
            check(con["facility_id"] not in opened, f"{con['id']}: 개설 금지 위반")
        elif kind == "allow_assignment":
            allowed[con["customer_id"]].add(con["facility_id"])
    check(len(result["periods"]) == len(par["periods"]), "입력과 결과의 기간 수가 다릅니다.")
    distance = {(fid, cid): float(distance_provider(f["lat"], f["lon"], c["lat"], c["lon"]))
                for fid, f in fs.items() for cid, c in cs.items()}
    check(all(isfinite(d) and d >= 0 for d in distance.values()), "거리 공급자가 유한한 0 이상 km를 반환하지 않았습니다.")
    groups = {"normal": ("large", "small"), "premium": ("premium",)} if par["separate_premium"] else {"mixed": tuple(_PRODUCT_VOLUME)}
    min_capacity = min((v["capacity_cbm"] for v in vs.values() if v["enabled"]), default=None)
    objective = 0.0
    for t, period in enumerate(result["periods"]):
        if t >= len(par["periods"]):
            break
        source = par["periods"][t]
        label = f"기간 {source['name']}"
        check(period["name"] == source["name"], f"{label}: 기간 이름 불일치")
        near(period["days"], source["days"], f"{label}: 운영일수")
        multiplier = par["demand_multiplier"] * source["demand_multiplier"]
        near(period["demand_multiplier"], multiplier, f"{label}: 적용 수요배수")
        demands = {cid: {p: floor(c["demand"][p] * multiplier + 0.5) for p in _PRODUCT_VOLUME} for cid, c in cs.items()}
        assignment_list = period["assignments"]
        assignment = {a["customer_id"]: a for a in assignment_list}
        check(len(assignment_list) == len(assignment), f"{label}: 고객별 배정이 중복되었습니다.")
        check(assignment.keys() == cs.keys(), f"{label}: 모든 입력 고객이 정확히 한 번 보고되어야 합니다.")
        facility_units = defaultdict(int)
        facility_load = defaultdict(float)
        costs = {key: 0.0 for key in ("fixed", "handling", "inbound", "transport_normal", "transport_premium", "penalty")}
        costs["fixed"] = sum(fs[fid]["fixed_cost"] * par["fixed_cost_weight"] for fid in opened & fs.keys())
        fulfilled = 0
        total_demand = sum(sum(d.values()) for d in demands.values())
        load_total = weighted_distance = max_distance = 0.0
        required_load = defaultdict(float)
        for cid, a in assignment.items():
            if cid not in cs:
                continue
            fid = a["facility_id"]
            q, unmet = a["quantities"], a["unmet"]
            check(set(q) == set(_PRODUCT_VOLUME), f"{label}/{cid}: 출고 상품 키 불일치")
            check(set(unmet) == set(_PRODUCT_VOLUME), f"{label}/{cid}: 미충족 상품 키 불일치")
            for p in _PRODUCT_VOLUME:
                check(integer(q[p]), f"{label}/{cid}/{p}: 출고 개수는 0 이상 정수여야 합니다.")
                check(integer(unmet[p]), f"{label}/{cid}/{p}: 미충족 개수는 0 이상 정수여야 합니다.")
                near(q[p] + unmet[p], demands[cid][p], f"{label}/{cid}/{p}: 수요 보존", 1e-6)
                if not par["allow_unmet"]:
                    check(unmet[p] == 0, f"{label}/{cid}/{p}: 미충족 금지 위반")
            units = sum(q[p] for p in _PRODUCT_VOLUME)
            load = sum(q[p] * _PRODUCT_VOLUME[p] for p in _PRODUCT_VOLUME)
            fulfilled += units
            costs["inbound"] += units * par["inbound_cost_per_unit"]
            costs["penalty"] += sum(unmet[p] for p in _PRODUCT_VOLUME) * par["unmet_penalty"]
            if fid is None:
                check(units == 0, f"{label}/{cid}: 미배정 고객에게 출고가 있습니다.")
                check(a["distance_km"] is None, f"{label}/{cid}: 미배정 고객의 거리는 null이어야 합니다.")
                continue
            check(fid in fs, f"{label}/{cid}: 알 수 없는 배정 DC {fid}")
            check(fid in opened, f"{label}/{cid}: 개설되지 않은 DC에 배정되었습니다.")
            check(units > 0, f"{label}/{cid}: 출고 없는 불필요한 배정입니다.")
            if fid not in fs:
                continue
            check(fs[fid]["enabled"], f"{label}/{cid}: 비활성 DC에 배정되었습니다.")
            if cid in allowed:
                check(fid in allowed[cid], f"{label}/{cid}: 허용 배정 DC 목록 위반")
            d = distance[fid, cid]
            near(a["distance_km"], d, f"{label}/{cid}: 거리 공급자 재계산", 1e-6)
            facility_units[fid] += units
            facility_load[fid] += load
            costs["handling"] += units * fs[fid]["handling_cost"]
            load_total += load
            weighted_distance += d * load
            if units:
                max_distance = max(max_distance, d)
            for group, products in groups.items():
                required_load[fid, cid, group] = sum(q[p] * _PRODUCT_VOLUME[p] for p in products)
            for con in active:
                kind = con["type"]
                if kind == "forbid_assignment" and con["customer_id"] == cid:
                    check(fid != con["facility_id"], f"{label}/{cid}/{con['id']}: 배정 금지 위반")
                elif kind in ("max_distance", "premium_distance") and con["customer_id"] in (None, cid):
                    served = units if kind == "max_distance" else q["premium"]
                    check(served == 0 or d <= con["value"] + _EPS, f"{label}/{cid}/{con['id']}: 배송 거리 제한 위반")
        trip_counts = {vid: 0 for vid in vs}
        reported_load = defaultdict(float)
        available_capacity = defaultdict(float)
        trip_keys = set()
        total_distance = 0.0
        for row in period["trips"]:
            fid, cid, group, vid = row["facility_id"], row["customer_id"], row["group"], row["vehicle_id"]
            key = (fid, cid, group, vid)
            check(key not in trip_keys, f"{label}: 동일 경로/운송군/차종 회차가 중복됩니다.")
            trip_keys.add(key)
            check(fid in fs and cid in cs and vid in vs and group in groups, f"{label}: 회차에 알 수 없는 ID/운송군이 있습니다.")
            if fid not in fs or cid not in cs or vid not in vs or group not in groups:
                continue
            count = row["trips"]
            check(integer(count) and count > 0, f"{label}/{cid}/{vid}: 보고 회차는 양의 정수여야 합니다.")
            check(vs[vid]["enabled"], f"{label}/{vid}: 비활성 차량이 사용되었습니다.")
            check(fid in opened, f"{label}/{fid}: 닫힌 DC의 차량 운행입니다.")
            check(cid in assignment and assignment[cid]["facility_id"] == fid, f"{label}/{cid}: 배정과 차량 출발 DC가 다릅니다.")
            capacity = count * vs[vid]["capacity_cbm"]
            near(row["capacity_cbm"], capacity, f"{label}/{cid}/{vid}: 총 차량 용량")
            check(number(row["load_cbm"]) and -_EPS <= row["load_cbm"] <= capacity + _EPS,
                  f"{label}/{cid}/{vid}: 차량 용량 초과 또는 음의 적재량")
            reported_load[fid, cid, group] += row["load_cbm"]
            available_capacity[fid, cid, group] += capacity
            group_demand = sum(demands[cid][p] * _PRODUCT_VOLUME[p] for p in groups[group])
            upper = ceil((group_demand - 1e-9) / min_capacity) if min_capacity and group_demand > 0 else 0
            check(count <= upper, f"{label}/{cid}/{vid}: 수요 기반 차량 회차 상한 위반")
            trip_counts[vid] += count
            d = distance[fid, cid]
            total_distance += count * 2 * d
            cost_key = "transport_premium" if group == "premium" else "transport_normal"
            costs[cost_key] += par["transport_cost_weight"] * count * (vs[vid]["fixed_cost"] + vs[vid]["cost_per_km"] * d)
        for key in required_load.keys() | reported_load.keys():
            near(reported_load[key], required_load[key], f"{label}/{key}: 운송군 적재량 보존", 1e-6)
            check(required_load[key] <= available_capacity[key] + _EPS, f"{label}/{key}: 운송군 차량 용량 부족")
        for vid, v in vs.items():
            if v["max_trips"] is not None:
                check(trip_counts[vid] <= v["max_trips"], f"{label}/{vid}: 차량 자체 일별 회차 상한 위반")
        costs["total"] = sum(costs.values())
        check(set(period["costs"]) == set(costs), f"{label}: 비용 항목은 계약의 7개 항목과 정확히 일치해야 합니다.")
        for key, value in costs.items():
            near(period["costs"][key], value, f"{label}: 비용 {key}", 0.05)
        reported_facilities = {f["id"]: f for f in period["facilities"]}
        check(len(reported_facilities) == len(period["facilities"]), f"{label}: 시설 보고행 중복")
        check(reported_facilities.keys() == fs.keys(), f"{label}: 모든 DC의 물량 보고가 필요합니다.")
        for fid, row in reported_facilities.items():
            if fid in fs:
                near(row["units"], facility_units[fid], f"{label}/{fid}: DC 출고 개수")
                near(row["load_cbm"], facility_load[fid], f"{label}/{fid}: DC 출고 부피")
                near(row["share"], facility_load[fid] / load_total if load_total else 0.0, f"{label}/{fid}: DC 부피 비중")
        kpis = {"open_dcs": len(opened), "total_demand": total_demand,
                "fulfilled_demand": fulfilled, "fulfillment_rate": fulfilled / total_demand if total_demand else 1.0,
                "total_trips": sum(trip_counts.values()), "total_distance_km": total_distance,
                "average_distance_km": weighted_distance / load_total if load_total else 0.0,
                "max_distance_km": max_distance}
        for key, value in kpis.items():
            near(period["kpis"][key], value, f"{label}: KPI {key}")
        check(period["kpis"]["trips_by_vehicle"] == trip_counts, f"{label}: 차종별 회차 KPI 불일치")
        for con in active:
            kind, value = con["type"], con["value"]
            if kind == "capacity":
                selected = [con["facility_id"]] if con["facility_id"] else fs
                for fid in selected:
                    capacity = fs[fid]["capacity_cbm"] if value is None else value
                    check(facility_load[fid] <= capacity * (fid in opened) + _EPS, f"{label}/{fid}/{con['id']}: DC 용량 위반")
            elif kind == "max_trips":
                count = trip_counts[con["vehicle_id"]] if con["vehicle_id"] else sum(trip_counts.values())
                check(count <= value, f"{label}/{con['id']}: 일별 회차 상한 위반")
            elif kind == "min_fulfillment":
                check(fulfilled + _EPS >= value * total_demand, f"{label}/{con['id']}: 최소 수요 충족률 위반")
            elif kind == "budget":
                check(costs["total"] <= value + max(0.05, value * 1e-8), f"{label}/{con['id']}: 일별 예산 위반")
            elif kind == "custom":
                rhs, operator = con["rhs"], con["operator"]
                lhs = _custom_lhs(con["terms"], opened, assignment, period["trips"], distance)
                slack = max(1e-6, (abs(rhs) + abs(lhs)) * 1e-9)
                satisfied = (lhs <= rhs + slack if operator == "<=" else
                             lhs >= rhs - slack if operator == ">=" else abs(lhs - rhs) <= slack)
                check(satisfied, f"{label}/{con['id']}: 사용자 정의 제약 위반 "
                                 f"(좌변 {lhs:,.6g} {operator} 우변 {rhs:,.6g})")
        objective += costs["total"] * source["days"]
    near(result["objective"], objective, "운영일수 가중 총 목적함수", 0.05)
    if "applied_constraints" in result:
        _audit_applied_constraints(result["applied_constraints"], active, check)


def _audit_applied_constraints(reported, active, check):
    """Compare the reported rules with the input's active rules.

    A result written before a schema field existed simply omits that field, so
    a plain equality test would reject every stored result after any schema
    growth. A missing field is therefore accepted only when the input leaves it
    at its declared default, which still rejects a report that drops a field
    carrying real content, such as a custom rule's terms.
    """
    defaults = {name: field.get_default(call_default_factory=True)
                for name, field in Constraint.model_fields.items()}
    check(isinstance(reported, list) and len(reported) == len(active),
          "적용 제약 수가 입력의 활성 제약과 다릅니다.")
    if not isinstance(reported, list):
        return
    for row, expected in zip(reported, active):
        if not isinstance(row, dict):
            check(False, "적용 제약 항목이 객체가 아닙니다.")
            continue
        label = row.get("id", "?")
        unexpected = sorted(set(row) - set(expected))
        check(not unexpected, f"적용 제약 {label}: 알 수 없는 항목 {unexpected}")
        for key, value in expected.items():
            check(row[key] == value if key in row else value == defaults.get(key),
                  f"적용 제약 {label}: {key} 불일치")
