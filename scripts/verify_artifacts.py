"""Re-audit saved results against their exact input snapshots without solving."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.schemas import Scenario
from backend.validation import validate_result


def main():
    records = []
    for path in sorted((ROOT / "artifacts").rglob("*.result.json")):
        scenario_file = path.with_name(path.name.replace(".result.json", ".scenario.json"))
        if not scenario_file.is_file():
            continue
        scenario = Scenario.model_validate_json(scenario_file.read_text(encoding="utf-8"))
        result = json.loads(path.read_text(encoding="utf-8"))
        check = validate_result(scenario, result)
        records.append({"file": str(path.relative_to(ROOT)), "status": result["status"],
                        "gap": result.get("mip_gap"), **check})
    report = {"total": len(records), "passed": all(r["passed"] for r in records), "records": records}
    output = ROOT / "artifacts" / "verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": report["total"], "passed": report["passed"]}))
    return 0 if report["passed"] and records else 1


if __name__ == "__main__":
    raise SystemExit(main())
