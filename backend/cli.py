"""Command-line interface for the same validated scenarios used by the web API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .data import SOURCE, default_scenario
from .schemas import Scenario


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="내일의집 물류 네트워크 CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    default = commands.add_parser("default", help="원본 Excel에서 검증된 기본 Scenario JSON 생성")
    default.add_argument("--source", type=Path, default=SOURCE, help="수요 XLSX 경로")
    default.add_argument("--output", type=Path, required=True, help="Scenario JSON 저장 경로")
    default.add_argument("--audit-output", type=Path, help="선택: 원본 검증 정보 JSON 저장 경로")
    solve = commands.add_parser("solve", help="Scenario JSON 또는 기본 Excel 시나리오 최적화")
    source = solve.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="Scenario JSON; 미지정 시 기본 Excel 사용")
    source.add_argument("--source", type=Path, default=SOURCE, help="기본 시나리오용 수요 XLSX")
    solve.add_argument("--output", type=Path, required=True, help="Result JSON 저장 경로")
    solve.add_argument("--time-limit", type=float, help="Solver 제한시간(초, 0.1~300)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "default":
            scenario, audit = default_scenario(args.source)
            write_json(args.output, scenario.model_dump(mode="json"))
            if args.audit_output:
                write_json(args.audit_output, audit)
            print(f"Scenario: {args.output.resolve()} ({audit['customers']} regions, {audit['total_units']} units)")
            return 0

        if args.input:
            scenario = Scenario.model_validate_json(args.input.read_text(encoding="utf-8-sig"))
        else:
            scenario, _ = default_scenario(args.source)
        if args.time_limit is not None:
            payload = scenario.model_dump(mode="json")
            payload["parameters"]["time_limit"] = args.time_limit
            scenario = Scenario.model_validate(payload)
        from .optimizer import solve

        result = solve(scenario)
        write_json(args.output, result)
        print(f"Result: {args.output.resolve()} | status={result.get('status')} | gap={result.get('mip_gap')}")
        if result.get("status") in ("optimal", "feasible_limit") and result.get("validation", {}).get("passed"):
            return 0
        return 1 if result.get("status") == "error" else 2
    except (OSError, ValueError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
