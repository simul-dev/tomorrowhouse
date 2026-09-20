# 선행연구와 적용 근거

조사·확인일: **2026-09-21**. 아래 자료는 논문 출판사, 저자 소속 대학 저장소, 저자 문서, 제품·Solver 공식 문서에서 확인했다. 논문 출판연도와 온라인 선공개 연도를 구분한다. 문헌의 실험 성능은 해당 연구의 조건에 한정되며 내일의집 데이터에서 재현한 결과로 취급하지 않는다. 초록만 확인된 자료는 그 범위를 명시한다.

## 문제 계열과 본 프로젝트의 위치

Facility Location Problem(FLP)은 후보 시설의 개설과 수요 공급 관계를 함께 결정한다. 시설별 처리 한도를 넣으면 Capacitated FLP(CFLP)가 된다. Location–Allocation은 입지와 수요 배정을 연결하는 의사결정 관점이다. 저자 공개 교재는 개설 이진변수, 수요보존, 개설–물량 연결, 용량제약을 제시하며, 수요별 상한을 이용한 제약이 큰 임의 상수보다 강한 LP 완화를 만드는 이유를 설명한다. [Pedroso 외, Facility location problems](https://scipbook.readthedocs.io/en/latest/flp.html)

**본 프로젝트의 해석:** Base는 DC 용량을 비활성화한 시설입지 모형에 단일 DC 배정, 정수 상품흐름, 상품군별 정수 직배송 회차와 서비스 거리제약을 결합한다. 용량 시나리오는 CFLP 확장이다. 이 명칭과 범위는 원본 사례를 기반으로 정한 연구자 분류이며, 아래 논문의 모형과 완전히 동일하다는 의미가 아니다.

| 자료 | 확인된 연구·기능 | 적용 및 차이 |
|---|---|---|
| Azizi & Hu (2020), *Multi-product pickup and delivery supply chain design with location-routing and direct shipment*, IJPE 226, 107648. [출판사 초록](https://www.sciencedirect.com/science/article/pii/S0925527320300475), [DOI](https://doi.org/10.1016/j.ijpe.2020.107648) | 입지·직접운송·집배송 경로를 통합한 MILP, 단일 상품 적재와 복수 상품 적재의 두 모형. 공개 초록·서론 확인. | 상품 혼재 정책을 분리해 비교할 근거. 내일의집은 방문 순서가 없으므로 이 논문의 VRP 부분은 도입하지 않는다. |
| Potoczki, Holzapfel, Kuhn & Sternbeck (2024), *Integrated cross-dock location and supply mode planning in retail networks*, IJPE 276, 109349. [저자 대학 원문](https://edoc.ku.de/id/eprint/34176/1/1-s2.0-S0925527324002068-main.pdf), [DOI](https://doi.org/10.1016/j.ijpe.2024.109349) | 크로스도크 개설, 직접/경유 운송, 공급 주기와 운송 수단을 통합한 MIP 및 계층 분해. 차량 단위 운임과 물량 결합을 다룬다. | 물량당 평균 단가만 사용하면 차량 정수성·혼재 효과를 놓칠 수 있다는 관련 근거. 여기서는 공급 주기·재고 대신 DC–지역별 차종 회차를 직접 결정한다. |
| Štádlerová, Schütz & Tomasgard (2024), *Multi-period facility location and capacity expansion with modular capacities and convex short-term costs*, COR 163, 106395. [출판사 초록·모형 설명](https://doi.org/10.1016/j.cor.2023.106395) | 다기간 개설·용량 확장, Lagrangian 완화, 동적계획 하한과 greedy 실행가능해. 실험에서 큰 문제에 대한 일반 Solver의 계산 부담을 보고한다. | 입지와 기간별 운영의 결합, 확장 시 분해 필요성을 뒷받침한다. 본 모형은 3년간 동일 개설 상태를 공유하며 기간 중 용량 확장을 결정하지 않는다. |
| Tordecilla 외 (온라인 2025; 권호 2026), *A sustainable facility location problem with vehicle allocation: an urban logistics case study*, JORS 77(2), 539–554. [저자 대학 기록·초록](https://pure.unisabana.edu.co/en/publications/a-sustainable-facility-location-problem-with-vehicle-allocation-a/), [DOI](https://doi.org/10.1080/01605682.2025.2489131) | Bogotá 도시물류 사례에서 허브 입지와 차량배정, 비용·배출량의 다목적 모형 및 사전식 해법을 제시한다. 초록·출판정보 확인. | 입지와 차종 결정을 함께 다룰 실무적 관련성. 본 구현은 물류비 단일 목적이며 탄소배출계수 자료가 없어 배출량 최적화를 주장하지 않는다. |
| Wu, Zhang, Zhang, Liang & Zhang (2026), *Benders decomposition for stochastic facility location and production planning*, COR 186, 107316. [출판사 초록·서론](https://www.sciencedirect.com/science/article/pii/S0305054825003454), [DOI](https://doi.org/10.1016/j.cor.2025.107316) | 수요의 지속적 변화가 있는 확률적 입지·생산계획에 ML을 이용한 Benders 분해를 제시한다. 2026년 2월 권호; DOI에는 2025가 포함된다. | 고정 평균수요 밖의 확률적 확장이 필요할 때 참고. 현재 Excel에는 확률분포가 없으므로 임의의 분포나 ML 기반 정확도 개선을 구현했다고 주장하지 않는다. |

## 거리와 연속·이산 입지

이산입지는 미리 정한 유한 후보에서 개설 여부를 정한다. 연속입지는 좌표 자체가 결정변수이므로 거리함수가 좌표와 함께 바뀐다. **본 프로젝트의 설계 판단:** 지도에서 좌표를 이동한 뒤 거리를 재계산하고 MILP를 다시 푸는 작업은 사용자가 후보를 조정하는 반복 분석이다. 연속공간의 전역 최적화를 수행한 것은 아니다. 초기 후보의 품질과 MILP 해의 품질도 분리해 평가해야 한다.

서비스 거리제약은 허용 DC–수요지역 연결을 결정한다. 공식 anyLogistix Paths 문서는 측지 직선거리와 실제 도로 경로를 구분하고 거리·시간을 외부 값으로 입력할 수도 있음을 설명한다. 본 도구는 Haversine을 명시적으로 사용하며, 향후 도로거리로 공급자를 교체할 수 있도록 거리 계산을 모델과 분리한다. [anyLogistix Paths](https://anylogistix.help/tables/paths.html)

## 실무 적용과 화면 흐름

anyLogistix 공식 Network Optimization 튜토리얼은 GFA로 찾은 잠재 위치에 개설비·처리비·운송비를 더해 네트워크를 평가하고, 해당 분석이 동적 특성을 포함하지 않는다고 설명한다. 별도의 Simulation 튜토리얼은 시간에 따른 재고·배송·통계를 다룬다. 이를 근거로 본 도구도 후보 편집 → 정적 최적화 → 시나리오 비교를 우선하고, 도착시간·대기열·재고 모사를 이번 범위와 구분한다. [Network Optimization](https://anylogistix.help/tutorial/tutorial-n-optimization-main.html), [공식 튜토리얼](https://anylogistix.help/tutorial/tutorials.html)

Wolf GmbH 사례는 Rothbaum Consulting이 GFA와 네트워크 최적화로 유럽의 DC 구성을 비교하고, 운송 유형·처리비·시설비를 반영한 사례다. 공식 페이지는 2024 콘퍼런스 발표임을 명시하고 5–10% 물류비, 약 35% 주행거리 감소를 보고한다. 이는 공급업체가 공개한 사례 결과이며 본 프로젝트의 예상 절감률로 전용하지 않는다. 화면의 지도·비용 분해·시나리오 비교 흐름을 참고하되 제품 디자인은 복제하지 않는다. [anyLogistix Wolf 사례](https://www.anylogistix.com/case-studies/strategic-network-design-to-reduce-supply-chain-costs-and-co2-emissions/)

## Solver 선택의 직접 근거

SciPy `optimize.milp`는 HiGHS를 호출하고 선형 제약, 변수별 정수성, 시간 제한, MIP gap 설정 및 상태 반환을 제공한다. HiGHS 공식 사이트는 MIP에 branch-and-cut을 사용하며 MIT 라이선스로 제공된다고 명시한다. 이에 따라 별도 상용 라이선스 없이 Python에서 수학모형을 실행하는 경로로 선택했다. 이는 사용성·기능 적합성 판단이며 다른 Solver보다 항상 빠르다는 주장이 아니다. [SciPy milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html), [HiGHS](https://highs.dev/)

본 규모에서의 실제 계산시간·gap·실행가능성은 후속 검증으로 측정한다. 문헌 성능 수치로 대체하지 않는다. 최종 선택과 비교 기준은 [methodology.md](methodology.md)에 기록한다.
