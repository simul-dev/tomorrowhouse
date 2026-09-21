import React from 'react';
import {Database, Ruler, Sparkles, Sigma, Split, Binary, ShieldCheck} from 'lucide-react';
import {Hint} from './components.jsx';

/* Academic framing of the case. The text here documents the formulation that
   backend/optimizer.py actually builds, so the two must be changed together. */

const CLASSES = [
  {
    tag: 'UFLP',
    name: '무용량 시설입지',
    detail: '경기 후보 중 실제 운영할 DC를 고르는 이진 결정 y_i와 일별 개설비 F_i가 목적식에 들어갑니다. ' +
      'Base 시나리오는 DC 처리용량 제약이 비활성이므로 무용량(Uncapacitated) 문제이고, ' +
      '정책 탭에서 처리용량을 켜면 용량제약 시설입지(CFLP)로 전환됩니다.',
  },
  {
    tag: 'TA',
    name: '수송 · 배정',
    detail: '각 수요지역은 최대 한 곳의 DC에만 배정됩니다(Σ_i a_ij ≤ 1). 단일 공급원 배정 위에서 ' +
      '상품별 출고량 q_ijp가 수요보존 Σ_i q_ijp + u_jp = D_jp 를 만족하는 수송문제 구조를 이룹니다.',
  },
  {
    tag: '+ 정수적재',
    name: '차종 배차',
    detail: '순수 UFLP+TA를 넘어서는 부분입니다. 일반·프리미엄 운송군별로 차종 k의 왕복 회차 n_ijgk를 ' +
      '정수로 결정해야 하므로 적재 용량 배낭(bin packing) 구조가 결합됩니다. 이 정수성 때문에 ' +
      '선형계획 완화만으로는 해를 쓸 수 없고 분지한정 탐색이 필요합니다.',
  },
];

const WORKFLOW = [
  {
    icon: Database, step: '01', name: '입력 감사',
    summary: '원본 Excel 66지역',
    detail: '헤더 자동 인식 후 수요·좌표·인구를 엄격 스키마로 검증하고, 파일 SHA-256과 상품 합계' +
      '(27,103개 / 7,107 CBM)를 기록합니다. 수식 셀·음수·중복 ID는 행 번호와 함께 거부합니다.',
  },
  {
    icon: Ruler, step: '02', name: '거리행렬',
    summary: 'Haversine d_ij',
    detail: '지구반경 6,371.0088km의 구면 대권거리로 후보 I × 지역 J 편도거리를 만듭니다. ' +
      '운임은 편도 d_ij, 운행거리 KPI는 왕복 2·d_ij로 분리해 계산합니다. 도로 경로가 아닙니다.',
  },
  {
    icon: Sparkles, step: '03', name: '후보 생성',
    summary: '탐욕 p-median',
    detail: '경기 31개 수요좌표에서 시작해, 전체 66지역의 CBM 가중 최근접거리 합을 가장 많이 줄이는 ' +
      '지점을 한 번에 하나씩 추가하는 greedy add 휴리스틱으로 후보 10개를 만듭니다. ' +
      '후보 생성만 휴리스틱이고 이후 개설·배정·배차는 통합 최적화합니다.',
  },
  {
    icon: Sigma, step: '04', name: '정식화',
    summary: '단일 MILP',
    detail: 'y_i(개설) · a_ij(배정) · q_ijp(출고) · u_jp(미충족) · n_ijgk(회차)를 모두 정수로 두고 ' +
      '개설비 + 처리비 + 공급비 + 운송비 + 패널티를 최소화합니다. 수요보존, 개설연계, 운송군 분리, ' +
      '적재용량, 프리미엄 거리, 선택적 용량·예산·충족률 제약을 하나의 모형에 담습니다.',
  },
  {
    icon: Split, step: '05', name: '구간 축약',
    summary: '정확 DP',
    detail: '구간을 가로지르는 자원제약(용량·회차·충족률·예산·사용자 정의)이 없으면 각 (DC, 지역) 구간의 ' +
      '물량·배차가 서로 독립입니다. 무한 정수 배낭 DP로 구간별 최적 계획을 미리 풀어 MILP에는 y와 a만 ' +
      '남깁니다. 휴리스틱이 아니라 동치 변환이며, 결합 제약이 하나라도 켜지면 전체 모형으로 되돌아갑니다.',
  },
  {
    icon: Binary, step: '06', name: '정수 탐색',
    summary: 'HiGHS 분지한정',
    detail: 'SciPy가 감싼 HiGHS의 branch-and-cut으로 풉니다. presolve를 켜고 상대 MIP gap과 ' +
      '제한시간으로 종료하며, 시간 제한에 걸린 해는 최적이 아니라 실행가능해로만 표시합니다.',
  },
  {
    icon: ShieldCheck, step: '07', name: '독립 검산',
    summary: 'Solver 무관 재계산',
    detail: '해 벡터를 보지 않고 결과 문서만으로 수요보존·배정유일성·거리제한·적재량·회차상한·용량·' +
      '사용자 정의 제약과 모든 비용 항목을 다시 계산합니다. 하나라도 어긋나면 결과를 폐기합니다.',
  },
];

export function ProblemBrief() {
  return <div className="problem-brief">
    <div className="breadcrumb">문제 정의 <span>/</span> NETWORK DESIGN</div>
    <h1>수도권 당일배송 물류거점 입지 · 배정 · 배차 통합 최적화</h1>
    <p>
      이천 CDC에서 경기도 DC를 거쳐 수도권 66개 고정 수요지역으로 소형가구를 당일배송한다.
      배송은 <b>DC → 단일 수요지역 → DC</b> 왕복 직배송이므로 방문 순서를 정하는 차량경로(VRP)가 아니다.
      대형 · 소형 · 프리미엄소형 세 상품의 일별 평균수요는 서로 독립이고, 프리미엄은 별도 차량으로
      편도 30km 안에서만 배송할 수 있다. 결정해야 할 것은 <b>어느 거점을 열고</b>,
      <b> 각 지역을 어느 거점에 배정하며</b>, <b>상품별로 얼마를 실어</b>,
      <b> 어떤 차종으로 몇 회 운행할지</b>이며 목적은 일별 총 물류비 최소화다.
    </p>
    <div className="problem-class">
      <span className="class-label">문제 유형</span>
      {CLASSES.map(c => <Hint key={c.tag} text={c.detail} label={`${c.tag} ${c.name} 설명`}>
        <span className="class-chip"><b>{c.tag}</b>{c.name}</span>
      </Hint>)}
    </div>
  </div>;
}

export function MethodWorkflow() {
  return <section className="workflow" aria-label="최적화 해법 워크플로우">
    <div className="workflow-head">
      <h2>해법 워크플로우</h2>
      <p>각 단계에 커서를 올리거나 키보드로 이동하면 사용한 알고리즘을 볼 수 있습니다.</p>
    </div>
    <ol className="workflow-track">
      {WORKFLOW.map(({icon: Icon, step, name, summary, detail}) => <li key={step}>
        <Hint text={detail} label={`${step} ${name} 알고리즘 설명`}>
          <div className="workflow-step">
            <span className="workflow-index"><Icon size={15} strokeWidth={1.8} /><i>{step}</i></span>
            <b>{name}</b>
            <small>{summary}</small>
          </div>
        </Hint>
      </li>)}
    </ol>
  </section>;
}
