# 내일의집 · Network Lab

수도권 **66개 수요지역의 거점 개설·단일 DC 배정·상품별 출고·차종별 직배송 회차**를 계산하는 로컬 웹 의사결정 도구입니다. 제공된 PDF와 Excel을 직접 분석했고 원본은 변경하지 않았습니다. 프리미엄 전용 운송, 제약 편집, 지도 후보 이동, 시나리오 비교와 3년 성장 분석을 지원합니다.

## 설치와 실행

Windows PowerShell, Python **3.12+**, Node.js **22.12+**가 필요합니다. 초기 패키지 설치와 OSM 배경지도 표시는 인터넷 연결을 사용합니다.

프로젝트 폴더에서:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

브라우저에서 **http://127.0.0.1:8000** 을 엽니다. 서버 종료는 `Ctrl+C`. 다른 포트는 `start.ps1 -Port 8001`로 지정합니다.

수동 설치 또는 macOS/Linux:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

개발 모드는 백엔드를 8000 포트로 실행한 뒤 `frontend`에서 `npm run dev`를 실행합니다. Vite가 `/api` 요청을 백엔드로 전달합니다. production build를 새로 생성했다면 서버를 재시작하세요.

## 사용 흐름

1. 원본 기반 Base 시나리오와 경기 후보 10개를 확인합니다.
2. 지도에서 DC를 선택하여 좌표·비용·용량을 편집하거나, 추가 모드로 후보를 추가합니다.
3. 프리미엄 거리·개설 수·용량 등 정책과 차종·수요 배수를 설정합니다.
4. 최적화를 실행하고 해 상태, gap, 비용 분해, 충족률과 상품별 미충족을 확인합니다.
5. 시나리오를 저장·복제하여 설정을 바꾸고 비교합니다. Excel 결과 또는 JSON 시나리오를 내려받습니다.

상세 사용법은 [사용 가이드](docs/user-guide.md), 입력 규격은 [데이터 형식](docs/data-format.md)을 참조하세요. 시나리오는 해당 브라우저의 localStorage에 저장되므로 JSON 백업을 권장합니다.

## 엔진 단독 실행·검증

```powershell
.\.venv\Scripts\python -X utf8 -m backend.cli default --output artifacts\base.scenario.json
.\.venv\Scripts\python -X utf8 -m backend.cli solve --input artifacts\base.scenario.json --output artifacts\base.result.json
.\.venv\Scripts\python -m pytest
```

민감도와 성장전략 비교:

```powershell
.\.venv\Scripts\python -X utf8 scripts\run_analysis.py --section all --time-limit 30 --gap 0.001
# 3년 내내 고정된 DC 용량을 추가한 성장 비교
.\.venv\Scripts\python -X utf8 scripts\run_analysis.py --section growth --growth-capacity 1776.75 --output artifacts\growth-capacity --time-limit 30
```

분석 JSON에는 입력 스냅샷·결과·원본 감사값이 포함되고 CSV에는 기간별 일비용과 운영일수 가중 누적비용을 분리 저장합니다. 동일 목적함수/기간에서만 비용을 비교하세요. 실패·시간제한·검산 실패도 결과에 기록합니다.

브라우저 테스트 설치는 `scripts\setup.ps1 -WithBrowserTests`; 실행 방법과 실제 검증 결과는 [검증 기록](docs/validation.md)에 있습니다. 일괄 기본 검증은 `scripts\check.ps1`입니다.

## 모형과 해석

MILP로 거점·배정·정수 물량·정수 회차를 통합합니다. Solver는 **SciPy / HiGHS**, 핵심 정수 탐색은 branch-and-cut입니다. 구간이 독립인 정책에서는 정확 동적계획으로 배차를 축약하고, 용량·회차·충족률·예산이 결합되면 전체 MILP를 사용합니다. 초기 후보는 경기 31지역의 가중 탐욕 입지 휴리스틱으로 선정합니다. 지도 좌표는 사용자가 조정하는 입력이며 연속공간 최적 좌표를 증명하지 않습니다.

- 비용 = 일별 거점 임대료 + 처리비 + CDC 공급비 + 일반/프리미엄 운송비 + 미충족 패널티.
- 운임은 PDF대로 **편도 km**, 운행거리 KPI는 **왕복 km**입니다. 지도 선은 도로 경로가 아닙니다.
- 프리미엄만 기본 30km 제한. 일반 화물은 더 멀리 배송할 수 있으므로 전체 최대거리 30km 초과가 반드시 위반은 아닙니다.
- Base DC 용량은 비활성. 활성화하면 CBM/일로 적용합니다. 차량 가용량은 대수가 아닌 회/일입니다.
- 공급비 2,000원/개, 패널티 200,000원/미충족 개는 원문 단위 불명확에 따른 명시적 가정입니다.
- 3년 분석은 현재 대비 1.2/1.44/1.728배, 매년 365일, 기간 전체 동일한 개설 결정입니다.

[문제정의](docs/problem-definition.md) · [선행연구](docs/literature-review.md) · [방법론](docs/methodology.md) · [수리모형](docs/mathematical-model.md) · [가정](docs/assumptions.md) · [아키텍처](docs/architecture.md)

## 프로젝트 구조

기본 결과는 **구리·수원·부천·용인 4곳, 541,155,890.88원/일, 충족률 99.406%, gap 0**입니다. 백엔드 67개 테스트, 실제 브라우저 10개 흐름, 저장된 입력·결과 28쌍 검산과 production build를 통과했습니다. 상세 수치는 [정책 보고서](docs/policy-recommendations.md)와 [검증 기록](docs/validation.md)을 참조하세요.

```text
backend/       입력 검증, 후보 생성, 거리, 최적화, 검산, API, CLI
frontend/      React / Vite / Leaflet 웹 UI
tests/         원본 대조, 손계산·정수열거, 정책, API·Solver 경계 검증
scripts/       설치·실행·일괄 분석·브라우저 검증
docs/          문제·문헌·모형·가정·사용법·검증·정책 제언
artifacts/     재현 가능한 시나리오·결과·비교 CSV
```

## 한계와 다음 개발

Haversine 대표점 거리는 도로·교통·도서 배송을 반영하지 않습니다. 실제 후보부지 적합성과 경기도 행정경계는 검증하지 않습니다. 정수상품 적재부피만 다루며 3차원 패킹·중량·차량 근무시간·실제 당일 도착시각·재고는 모형에 없습니다. 시간제한 해의 최적성은 미증명이며, Solver gap과 독립 검산 상태를 함께 확인해야 합니다.

다음 우선순위는 실제 부지 및 도로거리, 차량 운행시간 데이터, 수요 불확실성·모사 검증, 대규모 계산용 작업 큐/DB입니다. 상세 정책 제언과 수치는 [정책 보고서](docs/policy-recommendations.md), 요구사항별 구현은 [추적표](docs/requirements-traceability.md)에 정리했습니다. PPT, 원격 push, 외부 배포는 수행하지 않습니다. 원본 자료의 교육 목적 및 배포 제한은 원본 문서를 따릅니다.
