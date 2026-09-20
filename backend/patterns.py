"""Exact lane-pattern reduction for scenarios without coupled lane resources.

With capacity, fleet, fulfillment, and budget constraints absent, the freight
and product decisions of a fixed DC/customer/period are independent. Each
delivered unit has the same handling/inbound cost and avoids the same penalty.
For a given integer-CBM vehicle capacity, loading 0.2-CBM goods before 1-CBM
goods therefore maximizes that lane's net benefit. An unbounded integer
knapsack finds the cheapest fleet for every relevant total capacity.

The resulting optimal lane plans leave only shared facility-opening and
customer-assignment binaries in the MILP. This is an exact reformulation, not a
heuristic. Scenarios with any cross-lane resource limit use the full model.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import inf

import numpy as np


_COUPLED_TYPES = {"capacity", "max_trips", "min_fulfillment", "budget"}
_PRODUCTS = ("large", "small", "premium")
_VOLUME_FIFTHS = {"large": 5, "small": 1, "premium": 1}
_LOAD_ORDER = ("small", "premium", "large")


@dataclass
class LanePlan:
    quantities: dict[str, int]
    trips: dict[tuple[str, int], int]
    incremental_cost: float


@dataclass
class PatternReduction:
    model: object
    full_model: object
    plans: dict[tuple[int, int, int], LanePlan]
    data: dict
    demand: dict

    def expand(self, values: np.ndarray) -> np.ndarray:
        """Recover the original integer variable vector for the common audit."""
        full = np.zeros(len(self.full_model.cost), dtype=np.int64)
        original = self.full_model.index
        reduced = self.model.index
        for i in range(len(self.data["facilities"])):
            full[original["y", i]] = values[reduced["y", i]]
        for (t, j, p), quantity in self.demand.items():
            full[original["u", t, j, p]] = quantity
        for (t, i, j), plan in self.plans.items():
            if not values[reduced["a", t, i, j]]:
                continue
            full[original["a", t, i, j]] = 1
            for p, quantity in plan.quantities.items():
                full[original["q", t, i, j, p]] = quantity
                full[original["u", t, j, p]] -= quantity
            for (group, k), count in plan.trips.items():
                full[original["n", t, i, j, group, k]] = count
        return full


def build_pattern_reduction(data, active, full_model, distances, demand, groups):
    """Return an exact reduced model, or None when lane independence is absent."""
    if any(c["type"] in _COUPLED_TYPES for c in active):
        return None
    if any(v["max_trips"] is not None for v in data["vehicles"]):
        return None
    # A very large user-supplied demand must not allocate a DP array with one
    # entry per CBM. The original MILP has no demand-sized allocation and is an
    # exact, bounded-memory fallback in that case.
    largest_vehicle = max((v["capacity_cbm"] for v in data["vehicles"] if v["enabled"]), default=1)
    estimated_states = 0
    for t in range(len(data["parameters"]["periods"])):
        for j in range(len(data["customers"])):
            lane_count = sum(full_model.upper[full_model.index["a", t, i, j]] > 0
                             for i in range(len(data["facilities"])))
            for products in groups.values():
                target = (sum(demand[t, j, p] * _VOLUME_FIFTHS[p] for p in products) + 4) // 5
                states = target + largest_vehicle
                estimated_states += states * lane_count
                if (lane_count and states > 250_000) or estimated_states > 2_000_000:
                    return None
    model = full_model.__class__()
    fs, cs, par = data["facilities"], data["customers"], data["parameters"]
    periods = par["periods"]
    plans = {}
    # Keep the original objective's constant so the relative MIP gap is in the
    # same units and has the same denominator as the full formulation.
    baseline = sum(quantity * par["unmet_penalty"] * periods[t]["days"]
                   for (t, _j, _p), quantity in demand.items())
    constant = model.variable(("baseline",), 1, baseline)
    model.row([(constant, 1)], lower=1, upper=1)
    for i, f in enumerate(fs):
        cost = f["fixed_cost"] * par["fixed_cost_weight"] * sum(p["days"] for p in periods)
        model.variable(("y", i), int(f["enabled"]), cost)
    for t, period in enumerate(periods):
        for j in range(len(cs)):
            choices = []
            total_demand = sum(demand[t, j, p] for p in _PRODUCTS)
            if total_demand == 0:
                continue
            for i, facility in enumerate(fs):
                if full_model.upper[full_model.index["a", t, i, j]] == 0:
                    continue
                wanted = {p: demand[t, j, p] for p in _PRODUCTS}
                permitted = {p: int(full_model.upper[full_model.index["q", t, i, j, p]]) for p in _PRODUCTS}
                plan = _lane_plan(wanted, permitted, facility, data["vehicles"],
                                  par, distances[i, j], groups)
                if plan is None or not any(plan.quantities.values()):
                    continue
                plans[t, i, j] = plan
                a = model.variable(("a", t, i, j), 1, plan.incremental_cost * period["days"])
                model.row([(a, 1), (model.index["y", i], -1)], upper=0)
                choices.append((a, 1))
            model.row(choices, lower=-np.inf if par["allow_unmet"] else 1, upper=1)
    fi = {f["id"]: i for i, f in enumerate(fs)}
    for con in active:
        kind, value = con["type"], con["value"]
        if kind in ("min_dcs", "max_dcs"):
            model.row([(model.index["y", i], 1) for i in range(len(fs))],
                      lower=value if kind == "min_dcs" else -np.inf,
                      upper=value if kind == "max_dcs" else np.inf)
        elif kind in ("force_open", "forbid_open"):
            target = int(kind == "force_open")
            model.row([(model.index["y", fi[con["facility_id"]]], 1)], lower=target, upper=target)
    return PatternReduction(model, full_model, plans, data, demand)


def _lane_plan(wanted, permitted, facility, vehicles, par, distance, groups):
    if not par["allow_unmet"] and wanted != permitted:
        return None
    benefit = par["unmet_penalty"] - facility["handling_cost"] - par["inbound_cost_per_unit"]
    quantities = {p: 0 for p in _PRODUCTS}
    trips = {}
    incremental_cost = 0.0
    for group, products in groups.items():
        plan = _group_plan({p: permitted[p] for p in products}, vehicles, distance,
                           par["transport_cost_weight"], benefit, par["allow_unmet"])
        if plan is None:
            return None
        shipped, counts, cost = plan
        quantities.update(shipped)
        trips.update({(group, k): n for k, n in counts.items() if n})
        incremental_cost += cost
    return LanePlan(quantities, trips, incremental_cost)


def _group_plan(demand, vehicles, distance, transport_weight, benefit, allow_unmet):
    """Exact least-cost integer fleet and product quantities for one group."""
    zero = {p: 0 for p in demand}
    volume_fifths = sum(quantity * _VOLUME_FIFTHS[p] for p, quantity in demand.items())
    if volume_fifths == 0 or (allow_unmet and benefit <= 0):
        return zero, {}, 0.0
    choices = [(k, v["capacity_cbm"], transport_weight * (v["fixed_cost"] + v["cost_per_km"] * distance))
               for k, v in enumerate(vehicles) if v["enabled"]]
    if not choices:
        return (zero, {}, 0.0) if allow_unmet else None
    target = (volume_fifths + 4) // 5
    limit = target + max(capacity for _, capacity, _ in choices) - 1
    # Positive trip costs imply an optimal fleet never has a removable trip.
    # Thus total capacity < required capacity + largest available vehicle.
    dp = np.full(limit + 1, np.inf)
    prev = np.full(limit + 1, -1, dtype=np.int64)
    used = np.full(limit + 1, -1, dtype=np.int64)
    dp[0] = 0.0
    for capacity in range(1, limit + 1):
        best = inf
        for k, vehicle_capacity, trip_cost in choices:
            source = capacity - vehicle_capacity
            if source >= 0:
                value = dp[source] + trip_cost
                if value < best:
                    best = value
                    prev[capacity] = source
                    used[capacity] = k
        dp[capacity] = best
    best_cost = 0.0 if allow_unmet else inf
    best_capacity = 0
    best_shipped = zero
    for capacity in range(1, limit + 1):
        if not np.isfinite(dp[capacity]) or (not allow_unmet and capacity < target):
            continue
        remaining = capacity * 5
        shipped = {}
        for p in _LOAD_ORDER:
            if p in demand:
                shipped[p] = min(demand[p], remaining // _VOLUME_FIFTHS[p])
                remaining -= shipped[p] * _VOLUME_FIFTHS[p]
        cost = dp[capacity] - benefit * sum(shipped.values())
        if cost < best_cost:
            best_cost, best_capacity, best_shipped = cost, capacity, shipped
    if best_cost == inf:
        return None
    counts = {}
    cursor = best_capacity
    while cursor > 0:
        vehicle = int(used[cursor])
        counts[vehicle] = counts.get(vehicle, 0) + 1
        cursor = int(prev[cursor])
    return best_shipped, counts, float(best_cost)
