"""Improve fixed-opening evaluations by exact separation of independent years.

The shared opening vector is already fixed, so annual feasible plans can be
combined without changing any cross-year decision. Preserve prior results and
all subproblem evidence; retain the strongest valid sum-of-annual lower bound.
"""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.schemas import Scenario
from backend.optimizer import solve
from backend.validation import validate_result
from scripts.run_analysis import summarize, write_json, write_csv, SUMMARY_FIELDS, PERIOD_FIELDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "growth-capacity")
    parser.add_argument("--time-limit", type=float, default=20)
    args = parser.parse_args()
    directory = args.output
    rows = json.loads((directory / "growth_summary.json").read_text(encoding="utf-8"))
    evidence = []
    for strategy in ("myopic", "peak"):
        start = perf_counter()
        key = f"growth_{strategy}_evaluation"
        scenario = Scenario.model_validate_json((directory / f"{key}.scenario.json").read_text(encoding="utf-8"))
        old = json.loads((directory / f"{key}.result.json").read_text(encoding="utf-8"))
        design = json.loads((directory / f"growth_{strategy}_design.result.json").read_text(encoding="utf-8"))
        if not old["validation"]["passed"]:
            continue
        original = directory / f"{key}.original.json"
        if not original.exists():
            write_json(original, old)
        periods, annual_bounds = [], []
        for i, target in enumerate(scenario.parameters.periods):
            child = scenario.model_copy(deep=True)
            child.parameters.periods = [target.model_copy(update={"days": 1})]
            child.parameters.time_limit = args.time_limit
            child.name = f"{strategy} fixed opening / {target.name}"
            result = solve(child)
            subkey = f"refinement_{strategy}_year{i+1}"
            write_json(directory / f"{subkey}.scenario.json", child.model_dump())
            write_json(directory / f"{subkey}.result.json", result)
            options = [("original", old["periods"][i])]
            lower = 0.0
            if result["validation"]["passed"]:
                options.append(("annual_milp", result["periods"][0]))
                lower = result["objective"] * (1 - (result.get("mip_gap") or 0))
            if set(design["open_facilities"]) == set(old["open_facilities"]):
                dp = design["periods"][0]
                if abs(dp["demand_multiplier"]-target.demand_multiplier*scenario.parameters.demand_multiplier)<1e-10:
                    options.append(("known_design", dp))
                    lower = max(lower, design["objective"] / dp["days"] * (1-(design.get("mip_gap") or 0)))
            chosen, period = min(options, key=lambda x:x[1]["costs"]["total"])
            period = deepcopy(period)
            period.update(name=target.name, days=target.days)
            periods.append(period)
            annual_bounds.append(lower * target.days)
            evidence.append({"strategy":strategy,"period":target.name,"chosen":chosen,
                             "daily_cost":period["costs"]["total"],"daily_lower_bound":lower,
                             "annual_subproblem_status":result["status"]})
            print(f"{strategy} year{i+1}: {chosen}, {period['costs']['total']:.2f}", flush=True)
        improved = deepcopy(old)
        objective = sum(p["days"]*p["costs"]["total"] for p in periods)
        lower = max(sum(annual_bounds), old["objective"]*(1-(old.get("mip_gap") or 0)))
        gap = max(0.0, (objective-lower)/max(1,abs(objective)))
        improved.update(periods=periods, objective=objective, mip_gap=gap,
                        runtime_seconds=perf_counter()-start,
                        status="optimal" if gap<1e-8 else "feasible_limit",
                        message="개설 고정 후 연도별 독립 MILP와 기존 실행가능해를 조합한 최선 평가. gap은 유효 하한으로 재계산.")
        improved["diagnostics"] += [f"연도별 제한시간 {args.time_limit}초, 독립 연도 하한 합과 기존 하한 중 큰 값 사용.",
                                    f"Original upper bound {old['objective']}; refined lower bound {lower}."]
        improved["validation"] = validate_result(scenario, improved)
        if not improved["validation"]["passed"]:
            raise RuntimeError(improved["validation"])
        write_json(directory / f"{key}.result.json", improved)
        for pos, row in enumerate(rows):
            if row["experiment"] == key:
                metadata = {k:row[k] for k in ("reused_from","input_sha256","scenario_file","result_file","reference_experiment")}
                metadata["wall_seconds"] = improved["runtime_seconds"]
                rows[pos], _ = summarize(key,row["role"],scenario,improved,metadata)
    period_rows = []
    for row in rows:
        s = Scenario.model_validate_json((directory/row["scenario_file"]).read_text(encoding="utf-8"))
        r = json.loads((directory/row["result_file"]).read_text(encoding="utf-8"))
        _, pr = summarize(row["experiment"],row["role"],s,r,{})
        period_rows.extend(pr)
    write_json(directory/"growth_summary.json",rows)
    write_csv(directory/"growth_summary.csv",SUMMARY_FIELDS,rows)
    write_csv(directory/"growth_periods.csv",PERIOD_FIELDS,period_rows)
    write_json(directory/"refinement_evidence.json", evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
