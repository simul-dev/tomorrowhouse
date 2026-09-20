# 입력·출력 데이터 형식

## Excel

`.xlsx`, 최대 10MB(압축해제 합계 50MB), 수요지역 최대 500개. 처음 20행 안의 헤더를 찾아 유효한 수요 시트 하나를 자동 식별한다. 여러 수요 시트가 있으면 시트 이름을 명시해야 한다. 원본은 `Sheet1`이다.

| 정규 필드 | 원본 헤더 / 대체 헤더 | 형식 |
|---|---|---|
| id | 지역 / 수요지역 / customer_id / region / id | 고유 문자열 |
| population | 인구 / population | 0 이상 정수, 선택 열 |
| lat | 위도 / latitude / lat | −90~90 |
| lon | 경도 / longitude / lng / lon | −180~180 |
| large | 대형 / 대형가구 / large | 0 이상 정수 개/일 |
| small | 소형 / 소형가구 / small | 0 이상 정수 개/일 |
| premium | 프리미엄_소형 / 프리미엄 / premium | 0 이상 정수 개/일 |

헤더의 공백·밑줄·하이픈과 영문 대소문자는 정규화한다. 빈 행은 건너뛰지만 누락 셀, 중복 ID/헤더, 수식, NaN/Infinity, 음수/분수 수요, 잘못된 좌표는 오류로 반환한다. 서로 다른 지역이 같은 대표 좌표를 사용하면 경고를 반환한다. 인구 열이 없으면 0이며 최적화 가중치로 사용하지 않는다.

경기 ID `C_K...` 또는 `K_...`에서 초기 후보를 만든다. 다른 지역의 일반화된 데이터를 쓰려면 Scenario JSON에 후보를 직접 지정한다. Excel에는 거리·비용 열이 없으므로 PDF 기본 설정에서 제공하고 시나리오 JSON 검증으로 비정상 거리·비용을 차단한다.

Python에서 명시적 매핑 예:

```python
from backend.data import default_scenario
scenario, audit = default_scenario("demand.xlsx", sheet="Daily", mapping={"id": "고객명"})
```

HTTP 업로드는 multipart `file`, 선택 `sheet`, 선택 `mapping` JSON 문자열을 지원한다. 업로드는 기존 원본에 덮어쓰지 않는다.

## JSON

`backend/schemas.py`가 입력의 권위 있는 스키마다. 알 수 없는 필드·제약 타입·참조 ID, 중복 ID, 부정 비용/용량, 1 미만 또는 소수 CBM 차량은 거부한다. `/docs`에 FastAPI OpenAPI가 제공된다. `POST /api/validate`는 정상화된 Scenario를 반환한다.

전역 수요 배수 × 기간별 배수 적용 뒤 상품별 `floor(value+0.5)` 정수화. 비용 원/KRW, 처리량 CBM/일, 미충족 개/일, 충족률 0~1, 거리 km, 차량 회차 회/일이다. 기간 `days`는 비용 누적 가중치이고 수요를 하루 안에 days배로 늘리지 않는다.

구조와 예시는 [architecture.md](architecture.md)의 JSON 계약을 참조한다. Python에서 `default_scenario()[0].model_dump()` 또는 CLI로 완전한 입력을 얻는다.

## 결과

결과 JSON에는 해 상태, message, runtime_seconds, mip_gap, objective, 기간 공통 open_facilities, 기간별 비용·KPI·배정·차종별회차, 적용 제약, 독립 validation이 들어간다. 실행 가능한 해가 없으면 objective는 null이고 기간 결과는 비어 있다.

`trips.capacity_cbm`은 **해당 행의 회차 수 × 차량당 적재량**이다. `trips.load_cbm`은 운송군 물량을 차량별 잔여공간에 배분한 보고값으로 개별 차량 시간표는 아니다. `average_distance_km`은 출고 CBM 가중 편도거리, `total_distance_km`은 회차 가중 왕복거리이다.

Excel 내보내기는 Summary/Costs/Assignments/Trips/DCs/Scenario 시트로 구성되며 서버가 입력·결과 일치 여부를 재검산한다. 저장된 결과를 다른 입력에 붙여 내보내면 거부한다. Excel의 수식처럼 해석될 수 있는 문자열은 텍스트로 내보낸다.
