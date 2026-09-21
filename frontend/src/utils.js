export const fmt = (n, decimals = 0) => typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ko-KR', {maximumFractionDigits: decimals}) : '—';
export const money = n => typeof n !== 'number' ? '—' : n >= 100000000 ? `${fmt(n / 100000000, 2)}억` : `${fmt(n / 10000, 1)}만`;
export const percent = n => typeof n === 'number' ? `${fmt(n * 100, 1)}%` : '—';
export const uid = prefix => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
export const clone = obj => structuredClone(obj);
export const total = demand => Object.values(demand).reduce((s, n) => s + n, 0);
export const cbm = demand => demand.large + .2 * (demand.small + demand.premium);
export const STATUS = {optimal: '최적화 완료', feasible_limit: '시간 제한 · 실행가능해', infeasible: '실행 불가능', no_solution: '시간 내 해 없음', error: '검증 / 계산 오류'};
export const COSTS = [['fixed', '거점 임대료', '#12325e'], ['handling', '처리비', '#2f6fd0'], ['inbound', 'CDC 공급비', '#7fa8e0'], ['transport_normal', '일반 운송비', '#e0a020'], ['transport_premium', '프리미엄 운송비', '#b5730a'], ['penalty', '미충족 패널티', '#c0392b']];
export const validResult = r => !!r && ['optimal', 'feasible_limit'].includes(r.status) && r.validation?.passed === true;
export function explainError(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(e => typeof e === 'string' ? e : `${(e.loc || []).join(' → ')}: ${e.msg || JSON.stringify(e)}`).join('\n');
  return detail?.message ? `${detail.message}\n${(detail.errors || []).join('\n')}` : JSON.stringify(detail);
}
export async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let body; try { body = await response.json(); } catch { throw new Error(`서버 응답 오류 (${response.status})`); }
    throw new Error(explainError(body.detail || body));
  }
  return response;
}
export const jsonRequest = async (url, value) => (await request(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)})).json();
export function download(blob, name) {
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const downloadJSON = (value, name) => download(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json;charset=utf-8'}), name);
export const TEMPLATES = {
  min_dcs: {name: '최소 DC 수', value: 1, unit: '개', integer: true},
  max_dcs: {name: '최대 DC 수', value: 10, unit: '개', integer: true},
  capacity: {name: 'DC 처리용량', value: 700, unit: 'CBM/일', facility: true, optional: true},
  max_distance: {name: '전체 상품 배송거리', value: 100, unit: 'km', customer: true, optional: true},
  premium_distance: {name: '프리미엄 배송거리', value: 30, unit: 'km', customer: true, optional: true},
  force_open: {name: 'DC 강제 개설', facility: true},
  forbid_open: {name: 'DC 개설 금지', facility: true},
  allow_assignment: {name: '지역–DC 배정 허용', facility: true, customer: true},
  forbid_assignment: {name: '지역–DC 배정 금지', facility: true, customer: true},
  max_trips: {name: '차종 최대 회차', value: 500, unit: '회/일', integer: true, vehicle: true, optional: true},
  min_fulfillment: {name: '수요 충족률 하한', value: 1, unit: '비율 (0~1)', max: 1},
  budget: {name: '일별 예산 한도', value: 1000000000, unit: '원/일'},
  custom: {name: '사용자 정의 제약식', builder: true},
};

// Mirrors METRIC_FILTERS in backend/schemas.py. Every metric is a linear
// aggregate of the model variables, so the builder never needs an expression
// parser and the server can re-derive the same value from a result document.
export const METRICS = {
  open: {name: '개설 DC 수', unit: '개', filters: ['facility']},
  assigned: {name: '배정 지역 수', unit: '개', filters: ['facility', 'customer']},
  units: {name: '출고 물량', unit: '개', filters: ['facility', 'customer', 'product']},
  cbm: {name: '출고 부피', unit: 'CBM', filters: ['facility', 'customer', 'product']},
  unmet: {name: '미충족 물량', unit: '개', filters: ['customer', 'product']},
  trips: {name: '차량 회차', unit: '회', filters: ['facility', 'customer', 'vehicle', 'group']},
  distance: {name: '운행거리 (왕복)', unit: 'km', filters: ['facility', 'customer', 'vehicle', 'group']},
};
export const FILTER_KEYS = {facility: 'facility_id', customer: 'customer_id', vehicle: 'vehicle_id', product: 'product', group: 'group'};
export const PRODUCT_NAMES = {large: '대형', small: '소형', premium: '프리미엄'};
export const GROUP_NAMES = {normal: '일반', premium: '프리미엄', mixed: '가상 혼재'};
export const OPERATORS = {'<=': '≤', '>=': '≥', '==': '='};
export const emptyTerm = (metric = 'open') => ({coefficient: 1, metric, facility_id: null, customer_id: null, vehicle_id: null, product: null, group: null});

export function termLabel(term, scenario) {
  const meta = METRICS[term.metric];
  if (!meta) return '?';
  const named = (list, id) => list.find(x => x.id === id)?.name || id;
  const scope = [];
  if (term.facility_id) scope.push(named(scenario.facilities, term.facility_id));
  if (term.customer_id) scope.push(named(scenario.customers, term.customer_id));
  if (term.vehicle_id) scope.push(named(scenario.vehicles, term.vehicle_id));
  if (term.product) scope.push(PRODUCT_NAMES[term.product]);
  if (term.group) scope.push(GROUP_NAMES[term.group]);
  return `${meta.name}(${scope.length ? scope.join(', ') : '전체'})`;
}

export function formula(rule, scenario) {
  const left = (rule.terms || []).map((term, i) => {
    const coefficient = Number(term.coefficient ?? 1);
    const sign = i === 0 ? (coefficient < 0 ? '−' : '') : (coefficient < 0 ? ' − ' : ' + ');
    const size = Math.abs(coefficient);
    return `${sign}${size === 1 ? '' : `${fmt(size, 4)} · `}${termLabel(term, scenario)}`;
  }).join('');
  return `${left || '(항 없음)'} ${OPERATORS[rule.operator] || '≤'} ${fmt(rule.rhs ?? 0, 4)}`;
}
