"""Reproducible sensitivity runs and common-design three-year comparison.

Examples:
    python scripts/run_analysis.py --section sensitivity --time-limit 10
    python scripts/run_analysis.py --section growth --time-limit 30

Each section writes separate summaries and manifests, so the two sections may
be run independently. Existing named artifacts from earlier runs are replaced;
source inputs are never modified. No experiment is started on import.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data import SOURCE, default_scenario
from backend.schemas import Scenario

COST_FIELDS = ("fixed", "handling", "inbound", "transport_normal", "transport_premium", "penalty", "total")
SUMMARY_FIELDS = (
    "experiment", "role", "scenario", "status", "validation_passed", "objective_krw",
    "mip_gap", "runtime_seconds", "wall_seconds", "open_dcs", "open_facilities",
    "fixed_krw", "handling_krw", "inbound_krw", "transport_normal_krw",
    "transport_premium_krw", "penalty_krw", "total_krw", "demand_units",
    "fulfilled_units", "unmet_units", "fulfillment_rate", "total_trips",
    "total_distance_km", "periods", "modeled_days", "reference_experiment",
    "reused_from", "input_sha256", "scenario_file", "result_file", "message",
)
PERIOD_FIELDS = (
    "experiment", "role", "period", "days", "demand_multiplier", "status", "mip_gap",
    "daily_total_krw", "weighted_total_krw", "daily_fixed_krw", "daily_handling_krw",
    "daily_inbound_krw", "daily_transport_normal_krw", "daily_transport_premium_krw",
    "daily_penalty_krw", "daily_demand_units", "daily_fulfilled_units", "fulfillment_rate",
    "daily_trips", "daily_distance_km", "average_distance_km", "max_distance_km",
    "trips_by_vehicle",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validated_clone(base: Scenario, name: str, *, parameters: dict | None = None,
                    constraints: list[dict] | None = None, vehicle_id: str | None = None) -> Scenario:
    payload = base.model_dump(mode="json")
    payload["name"] = name
    payload["parameters"].update(parameters or {})
    if constraints is not None:
        payload["constraints"] = constraints
    if vehicle_id is not None:
        if vehicle_id not in {v["id"] for v in payload["vehicles"]}:
            raise ValueError(f"Unknown vehicle ID: {vehicle_id}")
        for vehicle in payload["vehicles"]:
            vehicle["enabled"] = vehicle["id"] == vehicle_id
    return Scenario.model_validate(payload)


def constraints_with(base: Scenario, constraint_type: str, value: float) -> list[dict]:
    rows = [c.model_dump(mode="json") for c in base.constraints if c.type != constraint_type]
    rows.append({"id": f"analysis-{constraint_type}", "type": constraint_type, "enabled": True, "value": value})
    return rows


def open_ids(result: dict) -> list[str]:
    return sorted(x if isinstance(x, str) else x["id"] for x in result.get("open_facilities", []))


def usable(result: dict) -> bool:
    return result.get("status") in ("optimal", "feasible_limit") and result.get("validation", {}).get("passed") is True


def summarize(experiment: str, role: str, scenario: Scenario, result: dict, metadata: dict) -> tuple[dict, list[dict]]:
    periods = result.get("periods") or []
    has_solution = usable(result)
    cost_totals = {name: 0.0 for name in COST_FIELDS}
    demand = fulfilled = trips = distance = days_total = 0.0
    period_rows = []
    for period in periods:
        days = period.get("days", 1)
        costs = period.get("costs", {})
        kpis = period.get("kpis", {})
        for name in COST_FIELDS:
            cost_totals[name] += days * costs.get(name, 0)
        days_total += days
        demand += days * kpis.get("total_demand", 0)
        fulfilled += days * kpis.get("fulfilled_demand", 0)
        trips += days * kpis.get("total_trips", 0)
        distance += days * kpis.get("total_distance_km", 0)
        period_rows.append({
            "experiment": experiment, "role": role, "period": period.get("name"), "days": days,
            "demand_multiplier": period.get("demand_multiplier"), "status": result.get("status"),
            "mip_gap": result.get("mip_gap"), "daily_total_krw": costs.get("total"),
            "weighted_total_krw": days * costs.get("total", 0),
            **{f"daily_{key}_krw": costs.get(key) for key in COST_FIELDS if key != "total"},
            "daily_demand_units": kpis.get("total_demand"), "daily_fulfilled_units": kpis.get("fulfilled_demand"),
            "fulfillment_rate": kpis.get("fulfillment_rate"), "daily_trips": kpis.get("total_trips"),
            "daily_distance_km": kpis.get("total_distance_km"), "average_distance_km": kpis.get("average_distance_km"),
            "max_distance_km": kpis.get("max_distance_km"),
            "trips_by_vehicle": json.dumps(kpis.get("trips_by_vehicle", {}), ensure_ascii=False, sort_keys=True),
        })
    ids = open_ids(result) if has_solution else []
    summary = {
        "experiment": experiment, "role": role, "scenario": scenario.name, "status": result.get("status"),
        "validation_passed": result.get("validation", {}).get("passed", False), "objective_krw": result.get("objective"),
        "mip_gap": result.get("mip_gap"), "runtime_seconds": result.get("runtime_seconds"),
        "open_dcs": len(ids) if has_solution else None, "open_facilities": "|".join(ids),
        **{f"{key}_krw": value if has_solution else None for key, value in cost_totals.items()},
        "demand_units": demand if has_solution else None, "fulfilled_units": fulfilled if has_solution else None,
        "unmet_units": demand - fulfilled if has_solution else None,
        "fulfillment_rate": (fulfilled / demand if demand else 1.0) if has_solution else None,
        "total_trips": trips if has_solution else None, "total_distance_km": distance if has_solution else None,
        "periods": len(periods), "modeled_days": days_total, "message": result.get("message", ""), **metadata,
    }
    return summary, period_rows


class Runner:
    def __init__(self, output: Path, section: str, audit: dict):
        self.output = output
        self.section = section
        self.audit = audit
        self.rows: list[dict] = []
        self.period_rows: list[dict] = []
        self.records: list[dict] = []
        self.cache: dict[str, tuple[str, dict]] = {}
        self.started = datetime.now(timezone.utc).isoformat()

    def run(self, key: str, scenario: Scenario, role: str = "sensitivity", reference: str = "") -> dict:
        from backend.optimizer import solve

        payload = scenario.model_dump(mode="json")
        hash_payload = {k: v for k, v in payload.items() if k != "name"}
        fingerprint = hashlib.sha256(json.dumps(hash_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        started = time.perf_counter()
        reused_from = ""
        if fingerprint in self.cache:
            reused_from, result = self.cache[fingerprint]
            print(f"[{self.section}] {key}: reuse {reused_from}", flush=True)
        else:
            print(f"[{self.section}] {key}: solving (limit {scenario.parameters.time_limit:g}s)", flush=True)
            result = solve(scenario)
            self.cache[fingerprint] = (key, result)
        elapsed = time.perf_counter() - started
        scenario_file = f"{key}.scenario.json"
        result_file = f"{key}.result.json"
        write_json(self.output / scenario_file, payload)
        write_json(self.output / result_file, result)
        metadata = {"wall_seconds": round(elapsed, 6), "reused_from": reused_from,
                    "input_sha256": fingerprint, "scenario_file": scenario_file,
                    "result_file": result_file, "reference_experiment": reference}
        summary, period_rows = summarize(key, role, scenario, result, metadata)
        self.rows.append(summary)
        self.period_rows.extend(period_rows)
        self.records.append({"experiment": key, "role": role, **metadata})
        self.flush()
        print(f"[{self.section}] {key}: {result.get('status')} | gap={result.get('mip_gap')} | validation={result.get('validation', {}).get('passed')}", flush=True)
        return result

    def skip(self, key: str, reference: str, reason: str) -> None:
        self.rows.append({"experiment": key, "role": "fixed_design_3year_evaluation", "status": "skipped",
                          "validation_passed": False, "reference_experiment": reference, "message": reason})
        self.flush()

    def flush(self) -> None:
        write_csv(self.output / f"{self.section}_summary.csv", SUMMARY_FIELDS, self.rows)
        write_csv(self.output / f"{self.section}_periods.csv", PERIOD_FIELDS, self.period_rows)
        write_json(self.output / f"{self.section}_summary.json", self.rows)
        write_json(self.output / f"{self.section}_manifest.json", {
            "section": self.section, "started_at_utc": self.started,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(), "source_audit": self.audit,
            "summary_units": "Costs, demand, trips and distance in summary are weighted by each period's modeled days; period CSV gives daily values.",
            "comparison_note": "Compare growth fixed-design evaluations over the same three years; design objectives use different horizons. Time-limited/gap solutions do not prove policy dominance.",
            "records": self.records,
        })


def sensitivity(base: Scenario, audit: dict, output: Path, quick: bool) -> Runner:
    runner = Runner(output, "sensitivity", audit)
    runner.run("base", base)
    for radius in ((20, 30, 40) if quick else (20, 25, 30, 35, 40)):
        # Preserve the exact base constraint IDs at 30 km so the fingerprint reuses it.
        constraints = None if radius == 30 else constraints_with(base, "premium_distance", radius)
        scenario = validated_clone(base, f"Premium distance {radius} km", constraints=constraints)
        runner.run(f"premium_{radius}km", scenario, reference="base")
    capacities = [("capacity_700cbm", 700)]
    if not quick:
        capacities.insert(0, ("capacity_25percent", audit["total_cbm"] * 0.25))
    for key, capacity in capacities:
        scenario = validated_clone(base, f"DC capacity {capacity:g} CBM", constraints=constraints_with(base, "capacity", capacity))
        runner.run(key, scenario, reference="base")
    runner.run("mixed", validated_clone(base, "Hypothetical mixed loading", parameters={"separate_premium": False}), reference="base")
    for vehicle_id, key in (("1t", "vehicle_1t_only"), ("3.5t", "vehicle_3_5t_only")):
        if quick and vehicle_id == "3.5t":
            continue
        runner.run(key, validated_clone(base, f"Only {vehicle_id}", vehicle_id=vehicle_id), reference="base")
    runner.run("demand_plus20percent", validated_clone(base, "Demand +20%", parameters={"demand_multiplier": 1.2}), reference="base")
    return runner


def growth(base: Scenario, audit: dict, output: Path) -> Runner:
    runner = Runner(output, "growth", audit)
    horizon = [
        {"name": "Growth year 1", "demand_multiplier": 1.2, "days": 365},
        {"name": "Growth year 2", "demand_multiplier": 1.44, "days": 365},
        {"name": "Growth year 3", "demand_multiplier": 1.728, "days": 365},
    ]
    for key, label, multiplier in (("myopic", "Year-1 optimized design", 1.2), ("peak", "Year-3 optimized design", 1.728)):
        design = validated_clone(base, label, parameters={"demand_multiplier": 1, "periods": [
            {"name": label, "demand_multiplier": multiplier, "days": 1},
        ]})
        result = runner.run(f"growth_{key}_design", design, role="single_year_design")
        evaluation_key = f"growth_{key}_evaluation"
        if not usable(result):
            runner.skip(evaluation_key, f"growth_{key}_design", "No validated feasible opening design; three-year comparison skipped.")
            continue
        selected = set(open_ids(result))
        constraints = [c.model_dump(mode="json") for c in base.constraints if c.type not in ("force_open", "forbid_open")]
        for facility in base.facilities:
            constraints.append({"id": f"fixed-design-{facility.id}", "type": "force_open" if facility.id in selected else "forbid_open",
                                "enabled": True, "facility_id": facility.id})
        fixed = validated_clone(base, f"{label}: fixed DCs, 3-year evaluation",
                                parameters={"demand_multiplier": 1, "periods": horizon}, constraints=constraints)
        runner.run(evaluation_key, fixed, role="fixed_design_3year_evaluation", reference=f"growth_{key}_design")
    multi = validated_clone(base, "Shared opening: 3-year integrated optimization", parameters={"demand_multiplier": 1, "periods": horizon})
    runner.run("growth_integrated", multi, role="integrated_3year_design_and_evaluation")
    return runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="내일의집 민감도 및 공통 DC 3년 성장 분석")
    parser.add_argument("--source", type=Path, default=SOURCE, help="원본 수요 XLSX")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "analysis")
    parser.add_argument("--time-limit", type=float, default=10, help="각 MILP 제한시간(초), 기본 10")
    parser.add_argument("--section", choices=("sensitivity", "growth", "all"), default="all")
    parser.add_argument("--quick", action="store_true", help="민감도에서 25/35 km, 25%% 용량, 3.5톤 단독 생략")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        base, audit = default_scenario(args.source)
        base = validated_clone(base, "Base · 2027", parameters={"time_limit": args.time_limit})
        runners = []
        if args.section in ("sensitivity", "all"):
            runners.append(sensitivity(base, audit, args.output, args.quick))
        if args.section in ("growth", "all"):
            runners.append(growth(base, audit, args.output))
        rows = [row for runner in runners for row in runner.rows]
        print(f"Analysis artifacts: {args.output.resolve()} | {len(rows)} records", flush=True)
        # Feasible limits are valid analysis outcomes, but failed/skipped runs remain visible.
        return 0 if all(row.get("status") in ("optimal", "feasible_limit") and row.get("validation_passed") for row in rows) else 2
    except (OSError, ValueError, ImportError) as exc:
        print(f"Analysis error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
