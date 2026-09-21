import React, {useState} from 'react';
import {BarChart3, ArrowUpRight, CheckCircle2, CircleDashed, Clock3, ChevronDown, Table2, Truck, Warehouse, Search, Info, HelpCircle} from 'lucide-react';
import {Empty, Hint} from './components.jsx';
import {fmt, money, percent, STATUS, COSTS, validResult, total} from './utils.js';

/* Each card explains what it measures and, where one exists, the exact term of
   the objective function it reports. Symbols match docs/mathematical-model.md. */
const HELP = {
  '총 물류비': ['선택한 기간의 하루치 목적함수 값입니다. 상품 매출과 구매원가는 이 물류비 목적에 포함하지 않습니다.',
    '총 물류비 = 거점 임대료 + 처리비 + CDC 공급비 + 일반 운송비 + 프리미엄 운송비 + 미충족 패널티'],
  '거점 임대료': ['개설한 거점에 매일 발생하는 임대료입니다. 1회성 투자비가 아니라 원문 §4.4의 일 평균 임대료 20,000,000원/DC이며, 하루 물동량과 무관하게 개설 여부로만 결정되는 고정비입니다.',
    'Σ_i F_i · y_i        F_i = 20,000,000원/일,  y_i = 개설 여부(0/1)'],
  '처리비': ['거점에서 상품 한 개를 입고·보관·피킹·상차하는 데 드는 비용입니다. 원문 §4.4의 SKU당 평균 50원이며, 배송하지 못한 물량에는 발생하지 않습니다.',
    'Σ h_i · q_ijp        h_i = 50원/개'],
  '운송비': ['거점에서 수요지역까지 왕복 직배송하는 트럭 운임의 합(일반 + 프리미엄)입니다. 회당 고정비에 편도거리 기반 변동비를 더합니다. 복귀거리는 원문 규정대로 운임에 두 번 반영하지 않습니다.',
    'Σ (f_k + c_k · d_ij) · n_ijgk        d_ij = 편도 km,  n = 회차'],
  '미충족 패널티': ['배송하지 못한 상품 한 개당 부과하는 기회손실·브랜드 손상 비용입니다. 실제 현금 지출이 아니라 서비스 실패의 가치를 비용으로 환산한 값이므로, 현금 물류비와 구분해서 읽어야 합니다.',
    'π · Σ u_jp        π = 200,000원/개'],
  'CDC 공급비': ['이천 통합물류센터에서 각 거점으로 상품을 채워 넣는 인바운드 운송비입니다. 원문 §4.4에 따라 거리와 무관한 건당 2,000원이며, 본 모형은 이를 충족 상품 1개당으로 해석했습니다(가정 A04). 거리와 무관하므로 전량 충족 시에는 어느 거점을 열어도 같은 금액이 되어 입지 결정에 영향을 주지 않습니다.',
    'b · Σ q_ijp        b = 2,000원/개'],
  '개설 DC': ['후보 중 실제로 임대해 운영하는 거점 수입니다. 다기간 분석에서도 모든 기간이 같은 개설 결정을 공유합니다.', 'Σ_i y_i'],
  '총 운행 횟수': ['하루에 발생하는 거점–수요지역 왕복 직배송 회차의 합입니다. 보유 차량 대수가 아니라 운행 횟수입니다.', 'Σ n_ijgk'],
  '총 운송거리': ['모든 회차의 실제 주행거리 합입니다. 운임은 편도 기준으로 계산하지만 트럭은 거점으로 복귀하므로, 이 지표만 왕복으로 집계합니다.', 'Σ 2 · d_ij · n_ijgk'],
  '충족 수요량': ['실제로 배송한 상품 개수입니다.', 'Σ q_ijp'],
  '수요 충족률': ['전체 상품 개수 기준 충족 비율입니다. 거리 제약으로 서비스가 불가능한 미충족뿐 아니라, 추가 운송비가 패널티보다 비싸서 발생하는 경제적 미충족도 포함되어 있습니다(가정 A11).', 'Σ q_ijp / Σ D_jp'],
  '평균 배송거리': ['출고 부피(CBM)로 가중한 편도 배송거리입니다. 물량이 많은 구간이 평균에 더 크게 반영됩니다.', 'Σ d_ij · (구간 출고 CBM) / Σ (구간 출고 CBM)'],
  '최대 배송거리': ['출고가 있는 구간 중 가장 먼 편도거리입니다. 프리미엄 30km 제한은 프리미엄 상품에만 적용되므로 이 값이 30km를 넘어도 제약 위반이 아닙니다.', 'max d_ij  (출고가 있는 구간)'],
  '차종별 회차': ['1톤·2.5톤·3.5톤 각 차종의 하루 운행 회차입니다. 차종마다 적재량과 운임이 달라 이 구성이 총 운송비를 좌우합니다.'],
  '최적화 상태': ['optimal은 주어진 후보와 모형에서 허용오차 내 최적해이고, 시간 제한 해는 최적성이 증명되지 않은 실행가능해입니다. gap은 현재 해와 하한의 상대 격차이며, 0이어도 후보 10개 자체의 최적성을 뜻하지는 않습니다.'],
};

export function Statistics({result, period, busy}) {
  const k = period?.kpis, c = period?.costs;
  const cards = [
    ['총 물류비', money(c?.total), '원/일', true], ['거점 임대료', money(c?.fixed), '원/일'], ['처리비', money(c?.handling), '원/일'],
    ['운송비', c ? money(c.transport_normal + c.transport_premium) : '—', '원/일'], ['미충족 패널티', money(c?.penalty), '원/일'], ['CDC 공급비', money(c?.inbound), '원/일'],
    ['개설 DC', fmt(k?.open_dcs), '개'], ['총 운행 횟수', fmt(k?.total_trips), '회/일'],
    ['총 운송거리', fmt(k?.total_distance_km, 1), 'km/일 · 왕복'], ['충족 수요량', fmt(k?.fulfilled_demand), '개/일'],
    ['수요 충족률', percent(k?.fulfillment_rate), '전체 상품'], ['평균 배송거리', fmt(k?.average_distance_km, 1), 'km · CBM 가중 편도'],
    ['최대 배송거리', fmt(k?.max_distance_km, 1), 'km · 편도'],
    ['차종별 회차', k ? Object.entries(k.trips_by_vehicle || {}).map(([name, n]) => `${name}: ${fmt(n)}`).join(' / ') : '—', '회/일', false, true],
    ['최적화 상태', busy ? '계산 중' : result ? STATUS[result.status] : '실행 전', result ? `${fmt(result.runtime_seconds, 2)}초 · gap ${percent(result.mip_gap)}` : '설정을 완료하고 실행하세요', false, true],
  ];
  return <div className="kpi-grid" aria-label="Overall Statistics">{cards.map(([label, value, unit, primary, small]) => {
    const [meaning, expression] = HELP[label] || [];
    return <article className={`kpi-card ${primary ? 'primary' : ''}`} key={label}><span>{label}</span><strong className={small ? 'small-value' : ''}>{value}</strong><small>{unit}</small>
      {meaning && <Hint className="kpi-help" label={`${label} 설명 보기`} text={<>
        <span className="hint-line">{meaning}</span>
        {expression && <span className="hint-formula">{expression}</span>}
      </>}><HelpCircle size={13} strokeWidth={2} /></Hint>}
    </article>;
  })}</div>;
}

export function ResultPanel({result, period, scenario, busy, onExport}) {
  const ok = validResult(result);
  const totalCost = period?.costs.total || 0;
  let end = 0;
  const gradient = COSTS.map(([key, , color]) => {const start = end; end += totalCost ? period.costs[key] / totalCost * 100 : 0; return `${color} ${start}% ${end}%`;}).join(',');
  return <aside className="results-panel panel"><div className="panel-title"><div><span className="eyebrow">OPTIMIZATION INSIGHTS</span><h2>분석 결과</h2></div><BarChart3 size={19} /></div>
    {!result ? <Empty icon={busy ? Clock3 : CircleDashed} title={busy ? '최적의 네트워크를 계산 중' : '다음 네트워크를 설계하세요'}>{busy ? '개설·배정·차종·회차를 함께 결정합니다. 실행가능성을 확인한 후 결과가 표시됩니다.' : '후보 거점과 정책을 조정하고 최적화를 실행하면 비용과 서비스 수준을 확인할 수 있습니다.'}</Empty> : !ok ? <div className="result-failure"><span className="status-chip danger">{STATUS[result.status]}</span><h3>설정 조건을 확인해 주세요</h3><p>{result.message}</p><p>거리·용량·회차·충족률·예산 조건을 검토한 후 다시 실행할 수 있습니다.</p><details open><summary>계산 진단</summary><ul>{[...(result.diagnostics || []), ...(result.validation?.errors || [])].map((d, i) => <li key={i}>{d}</li>)}</ul></details></div> : <>
      <div className="result-status" data-testid="result-status" role="status"><CheckCircle2 size={15} /><span>{STATUS[result.status]}</span><b>gap {percent(result.mip_gap)}</b></div>
      <div className="cost-visual"><div className="donut" role="img" aria-label="일별 비용 구성" style={{background: `conic-gradient(${gradient || '#e2e5ec 0% 100%'})`}}><div><span>일별 총비용</span><strong>{money(totalCost)}</strong><small>원</small></div></div></div>
      <div className="cost-list">{COSTS.map(([key, label, color]) => <div className="cost-row" key={key}><span><i style={{background: color}} />{label}</span><b>{money(period.costs[key])}<small> 원</small></b><div className="cost-bar"><i style={{width: `${totalCost ? period.costs[key] / totalCost * 100 : 0}%`, background: color}} /></div></div>)}</div>
      <div className="cumulative"><span>전체 계획기간 누적비용</span><strong>{money(result.objective)}<small> 원</small></strong><small>{result.periods.length}개 기간 · {fmt(result.periods.reduce((s, p) => s + p.days, 0))}일 합계</small></div>
      <div className="insight-note"><Info size={15} /><p>상품 {fmt(period.kpis.total_demand - period.kpis.fulfilled_demand)}개/일 미충족. 비용은 편도 운임 기준이며 총 운행거리에는 복귀를 포함합니다.</p></div>
      <button className="button full" aria-label="결과 Excel 다운로드" onClick={onExport}>결과 Excel 다운로드 <ArrowUpRight size={15} /></button>
      <details className="diagnostics"><summary>검증 및 계산 상세</summary><p>수요·적재·거점·거리·비용 검증 통과</p><p>계산시간 {fmt(result.runtime_seconds, 2)}초 · 상대 gap {percent(result.mip_gap)}</p><ul>{(result.diagnostics || []).map((d, i) => <li key={i}>{d}</li>)}</ul></details>
    </>}
  </aside>;
}

export function DetailTable({scenario, result, period}) {
  const [tab, setTab] = useState('assignments'); const [search, setSearch] = useState('');
  const customers = Object.fromEntries(scenario.customers.map(c => [c.id, c])); const facilities = Object.fromEntries(scenario.facilities.map(f => [f.id, f]));
  function appliedCapacity(id) {
    const rules = scenario.constraints.filter(c => c.enabled && c.type === 'capacity' && (!c.facility_id || c.facility_id === id));
    return rules.length ? `${fmt(Math.min(...rules.map(c => c.value ?? facilities[id]?.capacity_cbm)), 2)} CBM` : '비활성';
  }
  const match = text => String(text).toLowerCase().includes(search.toLowerCase());
  const tabs = [['assignments', '수요지역 배정', Table2], ['facilities', 'DC별 처리량', Warehouse], ['trips', '차종별 운행', Truck]];
  return <section className="detail-panel panel"><div className="detail-toolbar"><div className="detail-tabs" role="tablist" aria-label="결과 상세 탭">{tabs.map(([key, name, Icon]) => <button role="tab" aria-selected={tab === key} aria-controls="detail-table-panel" key={key} onClick={() => setTab(key)} className={tab === key ? 'selected' : ''}><Icon size={15} />{name}</button>)}</div><label className="search"><Search size={14} /><input aria-label="결과 검색" placeholder="지역 / DC 검색" value={search} onChange={e => setSearch(e.target.value)} /></label></div>
    <div className="table-scroll" id="detail-table-panel" role="tabpanel">
      {tab === 'assignments' && <table><thead><tr><th>수요지역</th><th>담당 DC</th><th>편도거리</th><th>대형</th><th>소형</th><th>프리미엄</th><th>미충족</th><th>상태</th></tr></thead><tbody>{period ? period.assignments.filter(a => match(`${customers[a.customer_id]?.name} ${facilities[a.facility_id]?.name || ''}`)).map(a => <tr key={a.customer_id}><td><b>{customers[a.customer_id]?.name || a.customer_id}</b></td><td>{facilities[a.facility_id]?.name || '미배정'}</td><td>{a.facility_id ? `${fmt(a.distance_km, 1)} km` : '—'}</td><td>{fmt(a.quantities.large)}</td><td>{fmt(a.quantities.small)}</td><td><span className="premium-text">{fmt(a.quantities.premium)}</span></td><td className={total(a.unmet) ? 'unmet-count' : ''}>{fmt(total(a.unmet))}</td><td><span className={`table-tag ${total(a.unmet) ? 'danger' : ''}`}>{total(a.unmet) ? '부분 / 미충족' : '충족'}</span></td></tr>) : scenario.customers.filter(c => match(c.name)).map(c => <tr key={c.id}><td><b>{c.name}</b></td><td>—</td><td>—</td><td>{fmt(c.demand.large)}</td><td>{fmt(c.demand.small)}</td><td className="premium-text">{fmt(c.demand.premium)}</td><td>—</td><td><span className="table-tag neutral">기준 수요</span></td></tr>)}</tbody></table>}
      {tab === 'facilities' && (period ? <table><thead><tr><th>거점</th><th>개설</th><th>충족 상품</th><th>처리량</th><th>물동량 비중</th><th>적용 용량</th></tr></thead><tbody>{period.facilities.filter(f => match(facilities[f.id]?.name)).map(f => <tr key={f.id}><td><b>{facilities[f.id]?.name || f.id}</b></td><td><span className={`table-tag ${result.open_facilities.includes(f.id) ? '' : 'neutral'}`}>{result.open_facilities.includes(f.id) ? '개설' : '미개설'}</span></td><td>{fmt(f.units)}개</td><td>{fmt(f.load_cbm, 1)} CBM</td><td>{percent(f.share)}</td><td>{appliedCapacity(f.id)}</td></tr>)}</tbody></table> : <Empty icon={Warehouse} title="최적화 후 DC별 부하를 확인하세요">개설 여부와 각 DC의 처리 물동량을 비교합니다.</Empty>)}
      {tab === 'trips' && (period ? <table><thead><tr><th>DC → 수요지역</th><th>운송군</th><th>차종</th><th>회차</th><th>적재량</th><th>총 가용공간</th><th>공간 사용률</th></tr></thead><tbody>{period.trips.filter(t => match(`${facilities[t.facility_id]?.name} ${customers[t.customer_id]?.name} ${t.vehicle_id}`)).map((t, i) => <tr key={i}><td><b>{facilities[t.facility_id]?.name} → {customers[t.customer_id]?.name}</b></td><td>{t.group === 'premium' ? '프리미엄' : t.group === 'mixed' ? '가상 혼재' : '일반'}</td><td>{scenario.vehicles.find(v => v.id === t.vehicle_id)?.name}</td><td>{fmt(t.trips)}회</td><td>{fmt(t.load_cbm, 1)} CBM</td><td>{fmt(t.capacity_cbm, 1)} CBM</td><td>{percent(t.capacity_cbm ? t.load_cbm / t.capacity_cbm : 0)}</td></tr>)}</tbody></table> : <Empty icon={Truck} title="차종별 직배송 회차를 계획합니다">일반·프리미엄 운송군의 회차와 적재량을 표시합니다.</Empty>)}
    </div><div className="table-caption">{period ? `${period.name} · 모든 물량과 회차는 1일 기준` : '업로드된 원본 기준 수요 · 최적화 결과는 아직 없습니다'}<span>행을 스크롤하여 전체 데이터 확인</span></div>
  </section>;
}
