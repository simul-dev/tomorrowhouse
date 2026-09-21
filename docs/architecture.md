# 아키텍처 및 데이터 계약

## 구성

`Excel → 검증/정규화 → 후보 생성 → Scenario JSON → 희소 MILP → HiGHS → 독립 결과 검산 → API/CLI → GIS UI`.

Python 3.12 / Pydantic / openpyxl / SciPy HiGHS로 UI 독립 엔진을 만들고 FastAPI로 제공한다. React + Vite + Leaflet로 PC 우선 반응형 화면을 만든다. OSM 타일에는 출처 표시를 유지한다. 타일이 네트워크로 불러와지지 않아도 좌표·레이어와 최적화는 동작한다. API는 로컬 바인딩하며 외부 서비스로 원본 수요를 전송하지 않는다. 타일 요청은 지도 표시 범위를 외부 OSM 서비스에 전달한다.

Solver와 거리엔진은 Python 호출 경계로 분리한다. Haversine의 `distance_km` 인터페이스를 향후 도로망 행렬 공급자로 교체한다. 업로드 파일은 메모리에서 검증하며 원본 파일에 저장/덮어쓰기하지 않는다. 저장·복제 시나리오는 브라우저 localStorage에 입력 및 계산 당시 결과 스냅샷으로 저장하며 JSON 백업을 제공한다. 변경 후 결과는 무효화하여 이전 위치의 결과가 최신인 것처럼 나타나지 않게 한다.

## Scenario JSON 계약

`backend/patterns.py`는 결합 자원제약이 없는 시나리오에 정확 DP→축약 MILP를 적용한다. 그 외에는 전체 희소 MILP를 유지한다. `solve(..., solver=...)`로 Solver adapter, `solve(..., distance_provider=...)`로 거리 공급자를 주입할 수 있다. 대체 거리로 생성한 결과의 독립 검산에도 같은 공급자를 전달한다.

```json
{
  "name": "Base · 2027",
  "customers": [{"id":"C_K수원시","name":"수원시","lat":37.2636,"lon":127.0286,"population":1190000,"demand":{"large":91,"small":799,"premium":281}}],
  "facilities": [{"id":"DC01","name":"수원 DC","lat":37.2636,"lon":127.0286,"fixed_cost":20000000,"handling_cost":50,"capacity_cbm":700,"enabled":true}],
  "vehicles": [{"id":"1t","name":"1톤","capacity_cbm":6,"fixed_cost":350000,"cost_per_km":15000,"enabled":true,"max_trips":null}],
  "parameters": {"demand_multiplier":1,"fixed_cost_weight":1,"transport_cost_weight":1,"unmet_penalty":200000,"inbound_cost_per_unit":2000,"allow_unmet":true,"separate_premium":true,"time_limit":30,"mip_rel_gap":0.01,"periods":[{"name":"2027","demand_multiplier":1,"days":1}]},
  "constraints": [{"id":"premium-distance","type":"premium_distance","enabled":true,"value":30}]
}
```

제약 type: `min_dcs,max_dcs,capacity,max_distance,premium_distance,force_open,forbid_open,allow_assignment,forbid_assignment,max_trips,min_fulfillment,budget,custom`. 선택 필드 `facility_id,customer_id,vehicle_id,label`. `custom`은 `value` 대신 `terms`(최대 40개), `operator`(`<=,>=,==`), `rhs`를 사용한다. 각 term은 `{coefficient, metric, facility_id?, customer_id?, vehicle_id?, product?, group?}`이고 metric은 `open,assigned,units,cbm,unmet,trips,distance`이다. metric이 지원하지 않는 필터, 알 수 없는 참조 ID, terms 없는 custom, custom이 아닌 type의 terms/rhs는 거부한다. 예: `{"id":"premium-floor","type":"custom","enabled":true,"operator":"<=","rhs":100,"terms":[{"coefficient":1,"metric":"unmet","product":"premium"}]}`. `capacity`의 value는 전체 DC 공통 상한이며 facility_id 지정 시 해당 DC만, value 미지정 시 DC 자체 capacity_cbm을 사용한다. 거리 customer_id를 지정하면 해당 지역에 적용한다. `min_fulfillment`는 0–1 비율. 알 수 없는 필드/type/참조 ID는 거부한다.

전역 `parameters.demand_multiplier`와 기간 `periods[].demand_multiplier`는 곱하여 적용한다. 기본 전역 배수 1에서 기간 배수 1.2/1.44/1.728을 사용한다. `transport_cost_weight`는 0보다 커야 한다. 모든 차량 비활성화 시 미충족 허용 여부에 따라 전량미충족 또는 infeasible이다. `max_distance`는 전체 상품에, `premium_distance`는 프리미엄에만 적용한다. 가상 `mixed` 운송비는 `transport_normal`에 집계한다. 평균거리는 출고 CBM 가중 편도거리이다. 할인율은 초기 구현에서 지원하지 않는다.

## API 및 결과 계약

- `GET /api/health`: 준비 상태.
- `GET /api/default`: 검증된 원본의 기본 Scenario.
- `POST /api/upload`: multipart `file` Excel → Scenario와 데이터 검증 정보.
- `POST /api/solve`: Scenario → Result (요청 중 UI busy, 백엔드 threadpool 실행).
- `POST /api/export`: `{scenario,result}` → 결과 Excel; UI CSV도 가능.
- `GET /`: 빌드된 프런트엔드. 개발 모드 Vite `/api` 프록시.

Result 공통: `status,message,runtime_seconds,mip_gap,objective,open_facilities,periods,validation,diagnostics,applied_constraints`. `status`는 `optimal,feasible_limit,infeasible,no_solution,error`. `validation`은 `passed,errors`이며 `objective`는 기간 가중 합계 원이다.

period: `name,days,demand_multiplier,costs,kpis,assignments,trips,facilities`. costs: `fixed,handling,inbound,transport_normal,transport_premium,penalty,total`. kpis: `open_dcs,total_demand,fulfilled_demand,fulfillment_rate,total_trips,total_distance_km,average_distance_km,max_distance_km,trips_by_vehicle`. assignments: `{customer_id,facility_id,distance_km,quantities:{large,small,premium},unmet:{large,small,premium}}`, 전체 고객 포함. trips: `{facility_id,customer_id,group,vehicle_id,trips,load_cbm,capacity_cbm}`. facilities: `{id,units,load_cbm,share}`. trip load는 운송군 물량을 차종별 가용공간에 배분한 보고값이며 그룹별 총량을 보존한다.

## 재현성과 실행

버전 고정 요구사항 파일과 npm lockfile을 제공한다. 원본 해시·합계 검증, 합성 소규모 최적성 사례, infeasible, 전체 데이터, 민감도, 다기간, API, 브라우저 동작, production build를 확인한다. 산출물은 `artifacts/` 아래 JSON/CSV와 검증 보고서로 남긴다. 원격 push/배포는 하지 않는다.

공식 구현 참조: [SciPy milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html), [HiGHS](https://highs.dev/), [Leaflet API](https://leafletjs.com/reference). 확인일 2026-09-21.
