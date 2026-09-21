import React, {useState} from 'react';
import {BarChart3, ArrowUpRight, CheckCircle2, CircleDashed, Clock3, ChevronDown, Table2, Truck, Warehouse, Search, Info} from 'lucide-react';
import {Empty} from './components.jsx';
import {fmt, money, percent, STATUS, COSTS, validResult, total} from './utils.js';

export function Statistics({result, period, busy}) {
  const k = period?.kpis, c = period?.costs;
  const cards = [
    ['총 물류비', money(c?.total), '원/일', true], ['거점 개설비', money(c?.fixed), '원/일'], ['처리비', money(c?.handling), '원/일'],
    ['운송비', c ? money(c.transport_normal + c.transport_premium) : '—', '원/일'], ['미충족 패널티', money(c?.penalty), '원/일'], ['CDC 공급비', money(c?.inbound), '원/일'],
    ['개설 DC', fmt(k?.open_dcs), '개'], ['총 운행 횟수', fmt(k?.total_trips), '회/일'],
    ['총 운송거리', fmt(k?.total_distance_km, 1), 'km/일 · 왕복'], ['충족 수요량', fmt(k?.fulfilled_demand), '개/일'],
    ['수요 충족률', percent(k?.fulfillment_rate), '전체 상품'], ['평균 배송거리', fmt(k?.average_distance_km, 1), 'km · CBM 가중 편도'],
    ['최대 배송거리', fmt(k?.max_distance_km, 1), 'km · 편도'],
    ['차종별 회차', k ? Object.entries(k.trips_by_vehicle || {}).map(([name, n]) => `${name}: ${fmt(n)}`).join(' / ') : '—', '회/일', false, true],
    ['최적화 상태', busy ? '계산 중' : result ? STATUS[result.status] : '실행 전', result ? `${fmt(result.runtime_seconds, 2)}초 · gap ${percent(result.mip_gap)}` : '설정을 완료하고 실행하세요', false, true],
  ];
  return <div className="kpi-grid" aria-label="Overall Statistics">{cards.map(([label, value, unit, primary, small]) => <article className={`kpi-card ${primary ? 'primary' : ''}`} key={label}><span>{label}</span><strong className={small ? 'small-value' : ''}>{value}</strong><small>{unit}</small>{primary && <ArrowUpRight size={17} />}</article>)}</div>;
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
