import React, {useEffect, useRef, useState} from 'react';
import {X, Save, Copy, Trash2, FolderOpen, Download, GitCompareArrows, Layers} from 'lucide-react';
import {Empty} from './components.jsx';
import {fmt, money, percent, downloadJSON, validResult, STATUS} from './utils.js';

export default function Scenarios({entries, onClose, onSave, onLoad, onDuplicate, onDelete, scenario}) {
  const dialog = useRef(null); const [selected, setSelected] = useState([]);
  useEffect(() => {dialog.current.showModal();}, []);
  const compared = entries.filter(e => selected.includes(e.id));
  return <dialog ref={dialog} className="scenario-dialog" onCancel={e => {e.preventDefault(); onClose();}} onClick={e => {if (e.target === dialog.current) onClose();}}><div className="dialog-inner">
    <div className="dialog-heading"><div><span className="eyebrow">SCENARIO WORKSPACE</span><h2>시나리오 보관함</h2><p>대안을 저장하고 동일한 기준에서 결과를 비교하세요.</p></div><button autoFocus className="icon-button" aria-label="시나리오 보관함 닫기" onClick={onClose}><X size={20} /></button></div>
    <div className="dialog-toolbar"><span>현재 작업: <b>{scenario.name}</b></span><button className="button primary-button" onClick={onSave}><Save size={15} />현재 시나리오 저장</button></div>
    {!entries.length ? <Empty icon={Layers} title="첫 번째 대안을 저장하세요">입력과 계산 결과를 이 브라우저에 함께 보관합니다. JSON 백업으로 다른 환경에 옮길 수 있습니다.</Empty> : <div className="saved-grid">{entries.map(e => <article className={`saved-card ${selected.includes(e.id) ? 'selected' : ''}`} key={e.id}><div className="saved-top"><label><input type="checkbox" aria-label={`${e.name} 비교 선택`} checked={selected.includes(e.id)} onChange={ev => setSelected(ev.target.checked ? [...selected, e.id] : selected.filter(id => id !== e.id))} />비교</label><button className="icon-button danger" aria-label={`${e.name} 삭제`} onClick={() => {onDelete(e.id); setSelected(selected.filter(id => id !== e.id));}}><Trash2 size={15} /></button></div><h3>{e.name}</h3><small>{new Date(e.savedAt).toLocaleString('ko-KR')}</small><div className="saved-cost"><strong>{validResult(e.result) ? money(e.result.objective) : '미계산'}</strong><span>{validResult(e.result) ? `원 / ${e.result.periods.reduce((n, p) => n + p.days, 0)}일` : '입력 시나리오'}</span></div><p>{e.scenario.facilities.length} 후보 · {e.scenario.parameters.periods.length} 기간 · {e.result ? STATUS[e.result.status] : '실행 전'}</p><div className="saved-actions"><button className="button" onClick={() => {onLoad(e); onClose();}}><FolderOpen size={13} />불러오기</button><button className="icon-button" aria-label={`${e.name} 복제`} title="복제" onClick={() => onDuplicate(e)}><Copy size={15} /></button><button className="icon-button" aria-label={`${e.name} JSON 백업`} title="JSON 백업" onClick={() => downloadJSON({version: 1, scenario: e.scenario, result: e.result}, 'tomorrowhouse-scenario.json')}><Download size={15} /></button></div></article>)}</div>}
    {compared.length > 0 && <section className="comparison"><h3><GitCompareArrows size={18} />선택한 시나리오 비교 <span>{compared.length}</span></h3><p>누적비용은 기간·운영일·수요 배수가 같은 시나리오끼리 비교하세요. 첫 기간 비용과 누적비용을 구분합니다.</p><div className="table-scroll"><table><thead><tr><th>지표</th>{compared.map(e => <th key={e.id}>{e.name}</th>)}</tr></thead><tbody>{[
      ['계획기간', e => `${e.scenario.parameters.periods.length}개 / ${e.scenario.parameters.periods.reduce((s, p) => s + p.days, 0)}일`],
      ['수요 배수 (기간별)', e => e.scenario.parameters.periods.map(p => fmt(p.demand_multiplier * e.scenario.parameters.demand_multiplier, 3)).join(' / ')],
      ['누적 총비용', e => validResult(e.result) ? `${money(e.result.objective)}원` : '—'],
      ['첫 기간 일별 비용', e => validResult(e.result) ? `${money(e.result.periods[0].costs.total)}원` : '—'],
      ['개설 DC', e => validResult(e.result) ? `${e.result.open_facilities.length}개` : '—'],
      ['첫 기간 충족률', e => validResult(e.result) ? percent(e.result.periods[0].kpis.fulfillment_rate) : '—'],
      ['첫 기간 회차', e => validResult(e.result) ? fmt(e.result.periods[0].kpis.total_trips) : '—'],
      ['첫 기간 운송거리', e => validResult(e.result) ? `${fmt(e.result.periods[0].kpis.total_distance_km, 1)}km` : '—'],
      ['MIP gap', e => percent(e.result?.mip_gap)], ['결과 상태', e => e.result ? STATUS[e.result.status] : '실행 전'],
    ].map(([label, render]) => <tr key={label}><th>{label}</th>{compared.map(e => <td key={e.id}>{render(e)}</td>)}</tr>)}</tbody></table></div></section>}
    <div className="dialog-footnote">브라우저 데이터를 삭제하면 보관함도 삭제됩니다. 필요한 시나리오는 JSON으로 백업하세요.</div>
  </div></dialog>;
}
