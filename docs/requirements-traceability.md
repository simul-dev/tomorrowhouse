# 요구사항과 구현·검증 연결

| 요구사항 | 구현 | 검증 근거 |
|---|---|---|
| PDF/Excel 직접 분석·원본 보존 | problem-definition, source-audit, data.py | 셀별 대조, SHA-256, test_data/test_api |
| 후보 설정과 실제 개설 구분 | data.generate_candidates, optimizer y | 경기31→10 재현성, 강제/금지/개설수 테스트 |
| C1 일반/프리미엄 별도 트럭 | q와 n의 운송군 분리 | 분리 시 추가회차, 혼재 비용차 손계산 |
| C2 프리미엄 편도30km | premium_distance 상품별 상한 | 일반 원거리 허용, 프리미엄 차단, 활성/비활성 |
| C3 차량 적재 | CBM 용량과 정수 회차 | 차종조합 전수열거, 독립 적재검산 |
| C4 보존·미충족·패널티 | q+u=D, allow_unmet, penalty | 부분출고 보존, 전량필수 infeasible; 경제적미충족은 A11 |
| C5 DC 용량 기본 비활성 | capacity 템플릿 | 활성/비활성 및 25%/700CBM 원본 실험 |
| C6 평균일·365일·성장 | parameters.periods | 기간별 배수·반올림·누적비용, y공유 |
| C7 단일지역 직배송 | DC–지역–운송군–차종별 회차 | 한 지역 단일DC, 왕복거리/편도운임 구분 |
| PDF §6 거리/용량/혼재/차종 분석 | run_analysis.py | artifacts/analysis 12기록(30km Base 재사용) |
| PDF §7 Myopic/Peak/3년통합 | 공통y, 고정설계 재평가 | 성장5기록+용량성장5기록, 동일1095일 비교 |
| 문제/방법론/수식/Solver/도구 구분 | methodology, mathematical-model, architecture | 별도 문서와 출처 |
| UI 독립 실행·Solver 교체 | CLI, solve solver/distance_provider 인자 | solver 상태/무해/정수성/대체거리 테스트 |
| 안전한 입력·내보내기 | Pydantic, Excel validation, server audit | invalid type/NaN/metadata/extra cost regression |
| GIS 후보 편집·레이어·수요 조회 | frontend/src/NetworkMap.jsx, Settings.jsx | 브라우저 기능 검증 |
| 정책12종/차량/파라미터/상태 | Settings.jsx, API solve | 엔진 템플릿 단위테스트+브라우저 흐름 |
| 템플릿 외 정책의 사용자 정의 제약 | schemas.Term, optimizer._term_entries, Settings.CustomRule | 템플릿 동치·계수·0/음수 우변·독립검산 거부 테스트 |
| 문제유형(UFLP+TA)·해법 단계 제시 | frontend/src/Overview.jsx | 브라우저 흐름에서 툴팁 표시 확인 |
| KPI·비용·배정·차량·DC 표 | Results.jsx | 엔진 독립검산+화면 결과 확인 |
| 시나리오 저장·복제·비교·백업 | frontend 앱/localStorage | 브라우저 저장·복제·재로딩·JSON 검증 |
| Excel 업로드·결과 다운로드 | API upload/export + 웹 UI | API 실제 XLSX 읽기+브라우저 파일 흐름 |
| 반응형·production build | frontend CSS/Vite | 데스크톱/모바일 화면, npm run build |

실행 기록·남은 경고·측정치는 [validation.md](validation.md), 정책 해석은 [policy-recommendations.md](policy-recommendations.md)에 기록한다. 원격 push, 외부 배포와 PPT는 범위에서 제외했다.
