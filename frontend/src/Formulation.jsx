import React from 'react';
import {ArrowLeft} from 'lucide-react';

/* This documents the model that backend/optimizer.py actually builds. Symbols
   follow docs/mathematical-model.md; the two must be changed together. */

const REASONS = [
  ['결정이 이산적이다',
   '거점은 열거나 열지 않거나이고, 상품은 개수 단위이며, 트럭은 1회나 2회를 뛰지 1.37회를 뛸 수 없다. ' +
   '선형계획으로 완화하면 "DC를 0.4개 연다"처럼 해석할 수 없는 해가 나오므로 이진·정수 변수가 필요하다.'],
  ['관계가 모두 선형이다',
   '임대료는 개설 여부에 비례하고, 처리비·공급비는 개수에 비례하며, 운임은 편도거리에 선형이고, 적재는 부피의 합이다. ' +
   '목적식과 제약에 비선형 항이 없으므로 혼합정수 "선형" 계획으로 충분하다.'],
  ['단계를 나누면 전체 최적이 아니다',
   '입지 → 배정 → 배차를 순서대로 풀면 각 단계는 최적이어도 전체는 최적이 아니다. 거리만 보고 거점을 먼저 정하면 ' +
   '6·14·17 CBM이라는 적재 단위가 만드는 계단형 운임을 반영하지 못한다. 그래서 다섯 종류의 결정을 한 모형에 함께 넣는다.'],
  ['최적성의 근거를 남길 수 있다',
   '분지한정은 해와 함께 하한을 계산하므로, 얻은 해가 최적에서 얼마나 떨어져 있는지를 MIP gap이라는 수치로 제시할 수 있다. ' +
   '메타휴리스틱으로는 이 보증을 만들 수 없다.'],
];

const SETS = [
  ['i ∈ I', '후보 물류거점 (기본 10개)'],
  ['j ∈ J', '고정 수요지역 (66개)'],
  ['p ∈ P', '상품 {대형, 소형, 프리미엄소형}, 부피 v_p = (1, 0.2, 0.2) CBM'],
  ['k ∈ K', '차종 {1톤, 2.5톤, 3.5톤}, 적재량 Q_k = (6, 14, 17) CBM'],
  ['g ∈ G', '운송군 {일반, 프리미엄} — 분리운송 제약 C1이 만드는 집합'],
  ['t ∈ T', '기간 (Base 1개, 성장분석 3개), 운영일수 w_t'],
];

const PARAMETERS = [
  ['D_jpt', '기간 t · 지역 j · 상품 p의 정수 수요'],
  ['d_ij', '거점 i와 지역 j 사이의 편도 거리 (km)'],
  ['F_i', '거점의 일 평균 임대료 = 20,000,000원/일'],
  ['h_i , b', '개당 처리비 50원, 개당 CDC 공급비 2,000원'],
  ['π', '미충족 1개당 패널티 = 200,000원'],
  ['f_k , c_k', '차종 k의 회당 고정비와 km당 변동비'],
  ['α , β', '임대료·운송비 시나리오 가중치 (기본 1)'],
];

const VARIABLES = [
  ['y_i', '{0, 1}', '거점 i를 개설하는가. 다기간에서도 모든 기간이 이 결정을 공유한다.'],
  ['a_ijt', '{0, 1}', '기간 t에 지역 j를 거점 i가 담당하는가.'],
  ['q_ijpt', '0 이상 정수', '거점 i가 지역 j로 보내는 상품 p의 개수.'],
  ['u_jpt', '0 이상 정수', '지역 j에서 충족하지 못한 상품 p의 개수.'],
  ['n_ijgkt', '0 이상 정수', '구간 (i, j)에서 운송군 g를 차종 k로 운행하는 왕복 회차.'],
];

const CONSTRAINTS = [
  ['수요 보존', 'Σ_i q_ijpt + u_jpt = D_jpt',
   '보낸 양과 못 보낸 양의 합은 언제나 수요와 같다. 물량이 사라지거나 생겨나지 않게 하는 항등식이다.'],
  ['단일 거점 배정', 'Σ_i a_ijt ≤ 1',
   '한 지역은 최대 한 곳의 거점만 담당한다. 전량 미충족이면 어느 거점도 담당하지 않으므로 등호가 아니라 부등호다.'],
  ['개설 연계', 'a_ijt ≤ y_i',
   '열지 않은 거점에는 배정할 수 없다. 입지 결정과 배정 결정을 묶는 고리이며, 이 식이 없으면 두 문제가 분리된다.'],
  ['배정 – 출고 연계', 'q_ijpt ≤ D_jpt · a_ijt      a_ijt ≤ Σ_p q_ijpt',
   '왼쪽은 담당하지 않는 거점이 출고하지 못하게 막고, 오른쪽은 출고가 0인데 담당으로만 잡히는 불필요한 배정을 제거한다.'],
  ['적재 용량 (운송군별)', 'Σ_{p∈g} v_p · q_ijpt ≤ Σ_k Q_k · n_ijgkt',
   '실어야 할 부피가 배차한 총 적재량을 넘을 수 없다. 일반과 프리미엄에 각각 걸리므로 C1의 분리운송이 여기서 강제된다.'],
  ['회차 상한', 'n_ijgkt ≤ M_jgt · a_ijt',
   '담당하지 않는 구간에는 차를 보내지 않는다. M_jgt = ⌈해당 운송군 수요 CBM ÷ 최소 차량 적재량⌉ 으로 둔 유효 상한이다.'],
  ['프리미엄 서비스 거리', 'd_ij > R  ⟹  q_ij,프리미엄,t = 0',
   'C2의 편도 30km 제약. 일반 상품에는 적용하지 않으므로 최대 배송거리가 30km를 넘어도 위반이 아니다.'],
  ['정수 · 이진 조건', 'y, a ∈ {0, 1}      q, u, n ∈ Z+  (0 이상 정수)',
   '이 조건이 문제를 선형계획에서 혼합정수계획으로 바꾸며, 분지한정 탐색이 필요해지는 이유가 된다.'],
];

const OBJECTIVE =
  'min  Σ_t w_t [ Σ_i α·F_i·y_i  +  Σ_ijp (h_i + b)·q_ijpt  +  Σ_ijgk β·(f_k + c_k·d_ij)·n_ijgkt  +  Σ_jp π·u_jpt ]';

export default function Formulation({onBack}) {
  return <section className="formulation" aria-label="MILP 정식화 상세">
    <div className="formulation-head">
      <button type="button" className="button back-button" onClick={onBack}><ArrowLeft size={15} />해법 워크플로우로</button>
      <div>
        <h2>MILP 정식화</h2>
        <p>거점 개설 · 지역 배정 · 상품별 출고 · 차종별 배차를 하나의 혼합정수선형계획으로 통합한다.</p>
      </div>
    </div>

    <div className="formulation-body">
      <div className="formulation-block">
        <h3>왜 이렇게 정식화했는가</h3>
        <ol className="reason-list">{REASONS.map(([title, body]) =>
          <li key={title}><b>{title}</b><span>{body}</span></li>)}</ol>
      </div>

      <div className="formulation-block">
        <h3>집합과 파라미터</h3>
        <dl className="symbol-list">{[...SETS, ...PARAMETERS].map(([symbol, meaning]) =>
          <div key={symbol}><dt>{symbol}</dt><dd>{meaning}</dd></div>)}</dl>
      </div>

      <div className="formulation-block">
        <h3>결정변수</h3>
        <dl className="symbol-list">{VARIABLES.map(([symbol, domain, meaning]) =>
          <div key={symbol}><dt>{symbol}<i>{domain}</i></dt><dd>{meaning}</dd></div>)}</dl>
      </div>

      <div className="formulation-block wide">
        <h3>목적함수 · 일별 총 물류비 최소화</h3>
        <pre className="formula-block">{OBJECTIVE}</pre>
        <p className="formula-note">
          왼쪽부터 <b>임대료</b>, <b>처리비와 CDC 공급비</b>, <b>운송비</b>, <b>미충족 패널티</b>다.
          임대료는 1회성 투자비가 아니라 매일 발생하므로 운영일수 w_t를 곱한다. 운임에는 원문 규정대로 <b>편도</b> d_ij를 쓰고,
          복귀거리는 운행거리 KPI에서만 2배로 집계한다. 상품 매출과 구매원가는 이 물류비 목적에 포함하지 않는다.
        </p>
      </div>

      <div className="formulation-block wide">
        <h3>제약식</h3>
        <ol className="constraint-list">{CONSTRAINTS.map(([name, expression, why]) => <li key={name}>
          <b>{name}</b>
          <pre className="formula-block small">{expression}</pre>
          <span>{why}</span>
        </li>)}</ol>
        <p className="formula-note">
          이 밖에 최소·최대 개설 수, 거점 처리용량, 일반 최대거리, 강제·금지 개설, 지역–거점 허용·금지, 차종 회차 상한,
          충족률 하한, 일별 예산, 사용자 정의 선형 제약을 정책 탭에서 켜고 끌 수 있다.
          어떤 제약이 실제로 모형에 들어갔는지는 결과의 <b>적용 제약</b> 목록에서 확인한다.
        </p>
      </div>
    </div>
  </section>;
}
