import React, {useState} from 'react';
import {Warehouse, SlidersHorizontal, Truck, Settings2, Plus, Trash2, MapPin, Check, RotateCcw} from 'lucide-react';
import {Field, Select, Toggle, Section, Reset, Hint} from './components.jsx';
import {fmt, uid, TEMPLATES, METRICS, FILTER_KEYS, PRODUCT_NAMES, GROUP_NAMES, OPERATORS, emptyTerm, formula} from './utils.js';

export default function Settings({scenario, edit, selected, onSelect, onFacility, deleteDC, addMode, setAddMode, result, busy, defaults}) {
  const [tab, setTab] = useState('facilities');
  const [template, setTemplate] = useState('max_dcs');
  const facility = scenario.facilities.find(f => f.id === selected);
  const tabs = [['facilities', '거점', Warehouse], ['policies', '정책', SlidersHorizontal], ['vehicles', '차량', Truck], ['parameters', '설정', Settings2]];
  const updateParameter = (key, value) => edit(s => {s.parameters[key] = value;});
  const updateConstraint = (id, patch) => edit(s => {Object.assign(s.constraints.find(c => c.id === id), patch);});
  function newConstraint(type) {
    const t = TEMPLATES[type]; const c = {id: uid('rule'), type, enabled: true, value: t.value ?? null};
    if (t.facility && !t.optional) c.facility_id = scenario.facilities[0].id;
    if (t.customer && !t.optional) c.customer_id = scenario.customers[0].id;
    // A non-binding starting point: adding the rule must not make the current
    // scenario infeasible before the user has written anything.
    if (t.builder) {c.value = null; c.operator = '<='; c.rhs = scenario.facilities.length; c.terms = [emptyTerm('open')];}
    return c;
  }
  const applied = new Set((result?.applied_constraints || []).map(c => typeof c === 'string' ? c : c.id));
  return <aside className="settings-panel panel"><div className="panel-title"><div><span className="eyebrow">SCENARIO SETUP</span><h2>네트워크 설정</h2></div><span className="count-tag">{scenario.facilities.length} DC</span></div>
    <div className="settings-tabs" role="tablist" aria-label="네트워크 설정 탭">{tabs.map(([key, label, Icon]) => <button key={key} role="tab" aria-selected={tab === key} aria-controls={`panel-${key}`} id={`tab-${key}`} onClick={() => setTab(key)} className={tab === key ? 'selected' : ''}><Icon size={16} />{label}</button>)}</div>
    <fieldset disabled={busy} className="settings-scroll" id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`}>
      {tab === 'facilities' && <>
        <div className="subheading"><span>후보 거점 <b>{scenario.facilities.length}</b></span><button className="text-button" onClick={() => setAddMode(!addMode)} aria-label="DC 추가 모드" aria-pressed={addMode} disabled={scenario.facilities.length >= 50}><Plus size={14} />추가</button></div>
        <div className="facility-list">{scenario.facilities.map((f, i) => <button key={f.id} className={`facility-row ${selected === f.id ? 'selected' : ''}`} onClick={() => onSelect(f.id)} aria-label={`${f.name} 선택`}><span className={`facility-number ${result?.open_facilities.includes(f.id) ? 'opened' : ''}`}>{String(i + 1).padStart(2, '0')}</span><span><b>{f.name}</b><small>{fmt(f.lat, 4)}, {fmt(f.lon, 4)}</small></span><span className={`dot ${f.enabled ? 'green' : ''}`} /></button>)}</div>
        {facility && <Section title="선택한 거점" eyebrow={facility.id} action={<button className="icon-button danger" aria-label="선택 DC 삭제" title="DC 삭제 (참조 제약도 삭제)" disabled={scenario.facilities.length <= 1} onClick={() => deleteDC(facility.id)}><Trash2 size={16} /></button>}>
          <Field label="DC 이름" type="text" value={facility.name} onChange={v => onFacility(facility.id, {name: v})} />
          <div className="fields-two"><Field label="DC 위도" min={-90} max={90} value={facility.lat} onChange={v => onFacility(facility.id, {lat: v})} /><Field label="DC 경도" min={-180} max={180} value={facility.lon} onChange={v => onFacility(facility.id, {lon: v})} /></div>
          <Field label="일 평균 임대료 (원/DC/일)" min={0} value={facility.fixed_cost} onChange={v => onFacility(facility.id, {fixed_cost: v})} />
          <div className="fields-two"><Field label="처리비 (원/개)" min={0} value={facility.handling_cost} onChange={v => onFacility(facility.id, {handling_cost: v})} /><Field label="용량 (CBM/일)" min={.2} step={.2} value={facility.capacity_cbm} onChange={v => onFacility(facility.id, {capacity_cbm: v})} /></div>
          <Toggle label="거점 운영 허용" checked={facility.enabled} onChange={v => onFacility(facility.id, {enabled: v})} hint="해제하면 이 거점은 개설되지 않습니다" />
          <p className="helper"><MapPin size={13} />지도에서 마커를 드래그해도 위치가 반영됩니다. 처리용량은 정책 탭에서 활성화합니다.</p>
        </Section>}
      </>}
      {tab === 'policies' && <>
        <Section title="제약조건 추가" eyebrow="CONSTRAINT LIBRARY"><Select label="제약 템플릿" value={template} onChange={setTemplate}>{Object.entries(TEMPLATES).map(([key, t]) => <option value={key} key={key}>{t.name}</option>)}</Select><button className="button full" onClick={() => edit(s => {s.constraints.push(newConstraint(template));})} disabled={scenario.constraints.length >= 200}><Plus size={15} />제약 추가</button></Section>
        {scenario.constraints.map((c, index) => { const t = TEMPLATES[c.type]; return <div className={`constraint-card ${!c.enabled ? 'inactive' : ''}`} key={c.id}>
          <div className="constraint-title"><b>{t.name}</b><div><Reset label={`${t.name} 기본값 복원`} onClick={() => {const original = defaults?.constraints.find(d => d.id === c.id); const reset = original || {...newConstraint(c.type), id: c.id}; edit(s => {s.constraints[index] = {...reset};});}} /><button className="icon-button" aria-label={`${t.name} 삭제`} onClick={() => edit(s => {s.constraints = s.constraints.filter(x => x.id !== c.id);})}><Trash2 size={14} /></button></div></div>
          <Toggle label={`${t.name} 활성화`} checked={c.enabled} onChange={v => updateConstraint(c.id, {enabled: v})} />
          {Object.hasOwn(t, 'value') && <Field label={`${t.name} 값 (${t.unit})`} min={0} max={t.max} step={t.integer ? 1 : 'any'} nullable={c.type === 'capacity'} value={c.value} onChange={v => updateConstraint(c.id, {value: v})} hint={c.type === 'capacity' ? '빈 값: 각 DC에 입력한 용량 사용' : c.type === 'budget' ? '기간별 일평균 총비용에 적용' : ''} />}
          {t.facility && <Select label={`${t.name} 대상 DC`} value={c.facility_id} onChange={v => updateConstraint(c.id, {facility_id: v || null})}>{t.optional && <option value="">전체 DC</option>}{scenario.facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</Select>}
          {t.customer && <Select label={`${t.name} 대상 지역`} value={c.customer_id} onChange={v => updateConstraint(c.id, {customer_id: v || null})}>{t.optional && <option value="">전체 지역</option>}{scenario.customers.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</Select>}
          {t.vehicle && <Select label="최대 회차 대상 차종" value={c.vehicle_id} onChange={v => updateConstraint(c.id, {vehicle_id: v || null})}><option value="">모든 차종 합계</option>{scenario.vehicles.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</Select>}
          {t.builder && <CustomRule rule={c} scenario={scenario} onChange={patch => updateConstraint(c.id, patch)} />}
          <small className={`applied-state ${applied.has(c.id) ? 'applied' : ''}`}>{applied.has(c.id) ? <><Check size={12} />이번 모델에 반영됨</> : c.enabled ? '다음 최적화에 적용 예정' : '비활성 · 모델에서 제외'}</small>
        </div>; })}
        <p className="helper">배정 허용을 추가하면 해당 지역은 지정한 DC 목록 내에서만 배정됩니다. 서로 충돌하는 조건은 실행 불가능 결과로 안내됩니다.</p>
      </>}
      {tab === 'vehicles' && <>
        <div className="inline-note">일별 직배송 회차를 결정합니다. 회차 상한은 보유 차량 대수가 아닙니다.</div>
        {scenario.vehicles.map((v, index) => {const patch = values => edit(s => {Object.assign(s.vehicles[index], values);}); return <Section key={v.id} title={`${v.name} 차량`} eyebrow="VEHICLE CAPACITY" action={<Reset label={`${v.name} 기본값 복원`} onClick={() => edit(s => {const original = defaults?.vehicles.find(x => x.id === v.id); if (original) s.vehicles[index] = {...original};})} />}>
          <Toggle label={`${v.name} 사용`} checked={v.enabled} onChange={enabled => patch({enabled})} />
          <div className="fields-two"><Field label={`${v.name} 적재량 (CBM)`} min={1} max={10000} step={1} value={v.capacity_cbm} onChange={capacity_cbm => patch({capacity_cbm})} /><Field label={`${v.name} 최대 회차`} min={0} step={1} nullable value={v.max_trips} onChange={max_trips => patch({max_trips})} hint="빈 값은 제한 없음" /></div>
          <Field label={`${v.name} 고정비 (원/회)`} min={1} value={v.fixed_cost} onChange={fixed_cost => patch({fixed_cost})} /><Field label={`${v.name} 변동비 (원/km)`} min={0} value={v.cost_per_km} onChange={cost_per_km => patch({cost_per_km})} />
        </Section>;})}
        <p className="helper">일반 상품과 프리미엄은 기본적으로 별도 운행합니다. 가상 혼재는 설정 탭에서 비교할 수 있습니다.</p>
      </>}
      {tab === 'parameters' && <>
        <Section title="수요와 비용" eyebrow="SCENARIO PARAMETERS" action={<Reset label="모든 파라미터 기본값 복원" onClick={() => edit(s => {s.parameters = structuredClone(defaults.parameters);})} />}>
          <Field label="수요 배수" min={0} max={10} step={.05} value={scenario.parameters.demand_multiplier} onChange={v => updateParameter('demand_multiplier', v)} hint="기간별 성장 배수와 곱하여 적용" />
          <input className="slider" type="range" min={0} max={3} step={.05} aria-label="수요 배수 슬라이더" value={scenario.parameters.demand_multiplier} onChange={e => updateParameter('demand_multiplier', +e.target.value)} />
          <div className="fields-two"><Field label="임대료 가중치" min={0} max={100} step={.1} value={scenario.parameters.fixed_cost_weight} onChange={v => updateParameter('fixed_cost_weight', v)} /><Field label="운송비 가중치" min={.01} max={100} step={.1} value={scenario.parameters.transport_cost_weight} onChange={v => updateParameter('transport_cost_weight', v)} /></div>
          <Field label="미충족 패널티 (원/개)" min={0} value={scenario.parameters.unmet_penalty} onChange={v => updateParameter('unmet_penalty', v)} /><Field label="CDC 공급비 (원/개)" min={0} value={scenario.parameters.inbound_cost_per_unit} onChange={v => updateParameter('inbound_cost_per_unit', v)} />
          <Toggle label="미충족 수요 허용" checked={scenario.parameters.allow_unmet} onChange={v => updateParameter('allow_unmet', v)} hint="해제 시 모든 상품 수요를 충족해야 합니다" />
          <Toggle label="프리미엄 분리 운송" checked={scenario.parameters.separate_premium} onChange={v => updateParameter('separate_premium', v)} hint="해제: 가상 혼재 시나리오 · 거리 제한 유지" />
        </Section>
        <Section title="계획기간" eyebrow="PLANNING HORIZON"><div className="two-buttons"><button className="button" onClick={() => updateParameter('periods', [{name: '2027', demand_multiplier: 1, days: 1}])}>Base 1일</button><button className="button" onClick={() => edit(s => {s.parameters.demand_multiplier = 1; s.parameters.periods = [1.2, 1.44, 1.728].map((m, i) => ({name: `성장 ${i + 1}년차`, demand_multiplier: m, days: 365}));})}>3년 성장 설정</button></div>
          {scenario.parameters.periods.map((p, i) => <div className="period-card" key={i}><div className="constraint-title"><b>기간 {i + 1}</b><button className="icon-button" disabled={scenario.parameters.periods.length <= 1} aria-label={`기간 ${i + 1} 삭제`} onClick={() => edit(s => {s.parameters.periods.splice(i, 1);})}><Trash2 size={14} /></button></div><Field label={`기간 ${i + 1} 이름`} type="text" value={p.name} onChange={v => edit(s => {s.parameters.periods[i].name = v;})} /><div className="fields-two"><Field label={`기간 ${i + 1} 수요 배수`} min={0} max={10} value={p.demand_multiplier} onChange={v => edit(s => {s.parameters.periods[i].demand_multiplier = v;})} /><Field label={`기간 ${i + 1} 운영일`} min={1} max={366} step={1} value={p.days} onChange={v => edit(s => {s.parameters.periods[i].days = v;})} /></div></div>)}
          <button className="text-button" disabled={scenario.parameters.periods.length >= 3} onClick={() => edit(s => {const names = new Set(s.parameters.periods.map(p => p.name)); let n = 1; while (names.has(`기간 ${n}`)) n++; s.parameters.periods.push({name: `기간 ${n}`, demand_multiplier: 1, days: 365});})}><Plus size={14} />기간 추가</button><p className="helper">다기간의 DC 개설은 공유하고 배정·물량·회차는 기간별로 결정합니다.</p>
        </Section>
        <Section title="계산 옵션"><div className="fields-two"><Field label="계산 제한시간 (초)" min={.1} max={300} value={scenario.parameters.time_limit} onChange={v => updateParameter('time_limit', v)} /><Field label="허용 MIP gap" min={0} max={.2} step={.001} value={scenario.parameters.mip_rel_gap} onChange={v => updateParameter('mip_rel_gap', v)} /></div><p className="helper">0.01은 1%입니다. 시간 제한에 도달하면 검증된 실행가능해와 gap을 표시합니다.</p></Section>
      </>}
    </fieldset>
    <div className="panel-bottom"><span className="dot green" />{scenario.constraints.filter(c => c.enabled).length}개 정책 활성 · 입력 변경 시 결과 재계산</div>
  </aside>;
}

const BUILDER_HELP = '좌변은 선택한 지표들의 선형 결합입니다. 각 지표(개설 수, 배정, 출고 물량·부피, 미충족, 회차, 운행거리)는 ' +
  '모형 변수의 합이므로 자유 수식을 문자열로 해석하지 않고도 같은 MILP 안에서 하나의 선형 행으로 들어갑니다. ' +
  '같은 정의로 결과 문서에서 좌변을 다시 계산해 독립 검산도 수행합니다. 다만 사용자 정의 제약은 구간 독립성을 깨뜨리므로 ' +
  '정확 DP 축약이 해제되고 전체 MILP를 풀기 때문에 계산시간이 늘어날 수 있습니다.';

function CustomRule({rule, scenario, onChange}) {
  const terms = rule.terms || [];
  const setTerm = (index, patch) => onChange({terms: terms.map((t, i) => i === index ? {...t, ...patch} : t)});
  function setMetric(index, metric) {
    const allowed = METRICS[metric].filters.map(name => FILTER_KEYS[name]);
    const scope = Object.fromEntries(Object.values(FILTER_KEYS).map(key => [key, allowed.includes(key) ? terms[index][key] ?? null : null]));
    setTerm(index, {metric, ...scope});
  }
  const pickers = {facility: ['대상 DC', scenario.facilities, '전체 DC'], customer: ['대상 지역', scenario.customers, '전체 지역'], vehicle: ['대상 차종', scenario.vehicles, '전체 차종']};
  return <div className="rule-builder">
    <div className="rule-formula"><span>수식</span><code aria-live="polite">{formula(rule, scenario)}</code></div>
    {terms.map((term, index) => <div className="rule-term" key={index}>
      <div className="rule-term-head"><span>항 {index + 1}</span><button className="icon-button" aria-label={`항 ${index + 1} 삭제`} disabled={terms.length <= 1} onClick={() => onChange({terms: terms.filter((_, i) => i !== index)})}><Trash2 size={13} /></button></div>
      <div className="fields-two">
        <Field label={`항 ${index + 1} 계수`} value={term.coefficient} onChange={v => setTerm(index, {coefficient: v === '' ? 0 : v})} />
        <Select label={`항 ${index + 1} 지표`} value={term.metric} onChange={v => setMetric(index, v)}>{Object.entries(METRICS).map(([key, m]) => <option key={key} value={key}>{m.name} · {m.unit}</option>)}</Select>
      </div>
      {METRICS[term.metric].filters.map(name => {
        const key = FILTER_KEYS[name];
        if (name === 'product') return <Select key={key} label={`항 ${index + 1} 상품`} value={term.product ?? ''} onChange={v => setTerm(index, {product: v || null})}><option value="">전체 상품</option>{Object.entries(PRODUCT_NAMES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</Select>;
        if (name === 'group') return <Select key={key} label={`항 ${index + 1} 운송군`} value={term.group ?? ''} onChange={v => setTerm(index, {group: v || null})}><option value="">전체 운송군</option>{Object.entries(GROUP_NAMES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</Select>;
        const [label, list, anyLabel] = pickers[name];
        return <Select key={key} label={`항 ${index + 1} ${label}`} value={term[key] ?? ''} onChange={v => setTerm(index, {[key]: v || null})}><option value="">{anyLabel}</option>{list.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</Select>;
      })}
    </div>)}
    <button className="text-button" disabled={terms.length >= 40} onClick={() => onChange({terms: [...terms, emptyTerm('trips')]})}><Plus size={14} />항 추가</button>
    <div className="fields-two">
      <Select label="부등호" value={rule.operator} onChange={v => onChange({operator: v})}>{Object.entries(OPERATORS).map(([key, sign]) => <option key={key} value={key}>{sign}</option>)}</Select>
      <Field label="우변 값" value={rule.rhs} onChange={v => onChange({rhs: v === '' ? 0 : v})} />
    </div>
    <Hint text={BUILDER_HELP} label="사용자 정의 제약식 동작 설명"><span className="rule-note">선형 결합으로 모형에 직접 추가 · DP 축약 해제</span></Hint>
  </div>;
}
