import React, {useEffect, useRef, useState} from 'react';
import {Network, Play, LoaderCircle, Upload, Download, Save, Copy, FolderOpen, ChevronDown, ArrowRight, X, CheckCircle2, AlertCircle, RotateCcw, FileJson, BookOpen, Warehouse} from 'lucide-react';
import NetworkMap from './NetworkMap.jsx';
import Settings from './Settings.jsx';
import {Statistics, ResultPanel, DetailTable} from './Results.jsx';
import Scenarios from './Scenarios.jsx';
import {clone, uid, request, jsonRequest, fmt, cbm, total, download, downloadJSON, validResult, STATUS} from './utils.js';

const STORAGE = 'tomorrowhouse.scenarios.v1';
function readSaved() {try {const saved = JSON.parse(localStorage.getItem(STORAGE) || '[]'); return Array.isArray(saved) ? saved.filter(e => e?.id && e.scenario?.customers && e.scenario?.facilities && e.scenario?.parameters) : [];} catch {return [];}}
export default function App() {
  const [scenario, setScenario] = useState(null), [defaults, setDefaults] = useState(null), [result, setResult] = useState(null);
  const [selected, setSelected] = useState(''), [periodIndex, setPeriodIndex] = useState(0), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [addMode, setAddMode] = useState(false);
  const [notice, setNotice] = useState(null), [saved, setSaved] = useState(readSaved), [showSaved, setShowSaved] = useState(false), [uploadOpen, setUploadOpen] = useState(false);
  const [sheet, setSheet] = useState(''), [mapping, setMapping] = useState(''), [elapsed, setElapsed] = useState(0);
  const version = useRef(0), operation = useRef(0), uploadRef = useRef(null), importRef = useRef(null);
  const tell = (message, error = false) => setNotice({message, error});
  useEffect(() => {loadDefault();}, []);
  useEffect(() => {if (!busy) return; setElapsed(0); const clock = setInterval(() => setElapsed(x => x + 1), 1000); return () => clearInterval(clock);}, [busy]);
  async function loadDefault() {
    const token = ++operation.current; setLoading(true);
    try {const data = await (await request('/api/default')).json(); if (token !== operation.current) return; setScenario(data); setDefaults(clone(data)); setSelected(data.facilities[0]?.id || ''); setResult(null); setPeriodIndex(0); version.current++;}
    catch (e) {tell(e.message, true);} finally {if (token === operation.current) setLoading(false);}
  }
  function edit(mutator) {
    if (busy || !scenario) return;
    setScenario(previous => {const next = clone(previous); mutator(next); return next;});
    version.current++; setResult(null); setPeriodIndex(0);
  }
  function facilityPatch(id, patch) {edit(s => {Object.assign(s.facilities.find(f => f.id === id), patch);});}
  function deleteDC(id) {edit(s => {s.facilities = s.facilities.filter(f => f.id !== id); s.constraints = s.constraints.filter(c => c.facility_id !== id);}); setSelected(scenario.facilities.find(f => f.id !== id)?.id || ''); tell('DC와 해당 DC를 참조하는 제약을 삭제했습니다.');}
  function addDC(lat, lon) {
    if (busy || scenario.facilities.length >= 50) return;
    const id = uid('DC'); edit(s => {s.facilities.push({id, name: `신규 DC ${s.facilities.length + 1}`, lat: +lat.toFixed(6), lon: +lon.toFixed(6), fixed_cost: 20000000, handling_cost: 50, capacity_cbm: 700, enabled: true});}); setSelected(id); setAddMode(false); tell('후보를 추가했습니다. 경기 소재 여부와 실제 부지 적합성은 별도 확인하세요.');
  }
  async function solve() {
    if (busy) return; const revision = version.current, token = ++operation.current; setBusy(true); setResult(null); setNotice(null); setAddMode(false);
    try {const data = await jsonRequest('/api/solve', scenario); if (revision !== version.current || token !== operation.current) return; setResult(data); setPeriodIndex(0); if (!validResult(data)) tell(data.message || '계산 조건을 확인하세요.', true); else tell(`최적화 결과를 검증했습니다. ${data.open_facilities.length}개 DC 개설 · ${STATUS[data.status]}`);}
    catch (e) {if (token === operation.current) tell(e.message, true);} finally {if (token === operation.current) setBusy(false);}
  }
  function persist(entries) {try {localStorage.setItem(STORAGE, JSON.stringify(entries)); setSaved(entries); return true;} catch {tell('브라우저 저장 공간이 부족합니다. 기존 시나리오를 삭제하거나 JSON으로 백업하세요.', true); return false;}}
  function saveCurrent() {const entry = {id: uid('saved'), name: scenario.name, savedAt: new Date().toISOString(), scenario: clone(scenario), result: result ? clone(result) : null}; if (persist([entry, ...saved])) tell('현재 입력과 결과를 시나리오 보관함에 저장했습니다.');}
  function duplicate(entry) {const s = clone(entry?.scenario || scenario); s.name = `${s.name} · 복제`.slice(0, 120); const r = entry ? entry.result : result; const copy = {id: uid('saved'), name: s.name, savedAt: new Date().toISOString(), scenario: s, result: r ? clone(r) : null}; if (persist([copy, ...saved])) tell('독립적인 시나리오 복사본을 저장했습니다.');}
  async function loadEntry(entry) {if (busy) return; const token = ++operation.current; setBusy(true); try {const validated = await jsonRequest('/api/validate', entry.scenario); if (token !== operation.current) return; version.current++; setScenario(validated); setResult(entry.result || null); setPeriodIndex(0); setSelected(validated.facilities[0]?.id || ''); setAddMode(false); tell('저장한 시나리오를 불러왔습니다.');} catch (e) {if (token === operation.current) tell(e.message, true);} finally {if (token === operation.current) setBusy(false);}}
  async function uploadExcel(file) {
    if (!file || busy) return; const token = ++operation.current; setBusy(true); setNotice(null);
    try {const form = new FormData(); form.append('file', file); if (sheet.trim()) form.append('sheet', sheet.trim()); if (mapping.trim()) {JSON.parse(mapping); form.append('mapping', mapping);}
      const data = await (await request('/api/upload', {method: 'POST', body: form})).json(); if (token !== operation.current) return; setScenario(data.scenario); setDefaults(clone(data.scenario)); setSelected(data.scenario.facilities[0]?.id || ''); setResult(null); setPeriodIndex(0); version.current++; setUploadOpen(false); tell(`Excel 검증 완료 · ${data.validation.customers}개 지역 / ${fmt(data.validation.total_units)}개 상품${data.validation.warnings?.length ? ` · ${data.validation.warnings.join(', ')}` : ''}`);
    } catch (e) {tell(e.message, true);} finally {if (token === operation.current) setBusy(false); if (uploadRef.current) uploadRef.current.value = '';}
  }
  async function importJSON(file) {
    if (!file || busy) return; setBusy(true);
    try {const parsed = JSON.parse(await file.text()); const data = await jsonRequest('/api/validate', parsed.scenario || parsed); version.current++; setScenario(data); setResult(null); setPeriodIndex(0); setSelected(data.facilities[0]?.id || ''); setAddMode(false); tell('JSON 입력을 검증하여 가져왔습니다. 결과는 다시 최적화하여 확인하세요.');}
    catch (e) {tell(e.message, true);} finally {setBusy(false); if (importRef.current) importRef.current.value = '';}
  }
  async function exportResult() {if (!validResult(result)) return; try {const response = await request('/api/export', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({scenario, result})}); download(await response.blob(), 'tomorrowhouse-result.xlsx'); tell('검증된 결과 Excel을 다운로드했습니다.');} catch (e) {tell(e.message, true);}}
  const currentPeriod = validResult(result) ? result.periods[Math.min(periodIndex, result.periods.length - 1)] : null;
  const inputUnits = scenario?.customers.reduce((s, c) => s + total(c.demand), 0);
  const inputVolume = scenario?.customers.reduce((s, c) => s + cbm(c.demand), 0);
  return <div className="app-shell">
    <nav className="side-rail" aria-label="기본 탐색"><a className="brand-symbol" href="/" aria-label="내일의집 홈"><Warehouse size={24} /></a><span className="rail-line" /><button className={!showSaved ? 'rail-button active' : 'rail-button'} aria-label="네트워크 화면" title="네트워크" onClick={() => setShowSaved(false)}><Network size={21} /></button><button className={showSaved ? 'rail-button active' : 'rail-button'} disabled={!scenario || busy} aria-label="시나리오 보관함" title="시나리오 보관함" onClick={() => setShowSaved(true)}><FolderOpen size={21} /></button><div className="rail-bottom"><span>NL</span><small>v1.0</small></div></nav>
    <div className="main-shell"><header className="topbar"><div className="brand"><b>내일의집<span>NETWORK LAB</span></b><i /><span>물류 네트워크 의사결정</span></div><div className="topbar-right"><span className="local-badge"><i />LOCAL WORKSPACE</span><button className="icon-button" aria-label="사용 안내" title="사용 안내" onClick={() => tell('① 거점을 지도에서 편집 ② 정책·차량·수요 설정 ③ 최적화 실행 ④ 결과 확인 후 시나리오 저장·비교. 모든 입력 변경은 기존 결과를 초기화합니다.')}><BookOpen size={19} /></button></div></header>
      <main className="workspace">
        <div className="page-heading"><div><div className="breadcrumb">WORKSPACE <span>/</span> NETWORK DESIGN</div><h1>더 나은 연결, 더 효율적인 내일.</h1><p>거점의 위치부터 마지막 직배송까지, 하나의 네트워크로 설계하세요.</p></div><span className="workspace-badge"><span className="dot green" />수도권 · 가구 배송</span></div>
        {notice && <div className={`notice ${notice.error ? 'error' : ''}`} role={notice.error ? 'alert' : 'status'}>{notice.error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}<span>{notice.message}</span><button className="icon-button" aria-label="알림 닫기" onClick={() => setNotice(null)}><X size={16} /></button></div>}
        {loading || !scenario ? <div className="loading-screen"><Network size={40} /><h2>{loading ? '네트워크 데이터를 준비하고 있습니다' : '데이터를 불러오지 못했습니다'}</h2><p>원본 수요와 후보 DC를 확인합니다.</p>{!loading && <button className="button" onClick={loadDefault}>다시 불러오기</button>}</div> : <>
          <section className="scenario-toolbar" aria-label="시나리오 작업"><div className="scenario-name"><span>현재 시나리오</span><input aria-label="시나리오 이름" maxLength={120} value={scenario.name} disabled={busy} onChange={e => edit(s => {s.name = e.target.value;})} /><span className="draft-tag">{validResult(result) ? '계산 완료' : '편집 중'}</span></div><div className="toolbar-actions"><button className="button" disabled={busy} onClick={() => setUploadOpen(!uploadOpen)} aria-expanded={uploadOpen}><Upload size={15} />Excel 업로드</button><button className="icon-button" disabled={busy} aria-label="JSON 가져오기" title="JSON 가져오기" onClick={() => importRef.current.click()}><FileJson size={17} /></button><button className="icon-button" disabled={busy} aria-label="현재 JSON 백업" title="현재 JSON 백업" onClick={() => downloadJSON({version: 1, scenario, result}, 'tomorrowhouse-scenario.json')}><Download size={17} /></button><span className="toolbar-divider" /><button className="icon-button" disabled={busy} aria-label="현재 시나리오 복제" title="복제" onClick={() => duplicate()}><Copy size={16} /></button><button className="button" disabled={busy} onClick={saveCurrent}><Save size={15} />저장</button><button className="button" disabled={busy} onClick={() => setShowSaved(true)}><FolderOpen size={15} />비교 · 보관함</button><button className="button primary-button solve-button" onClick={solve} disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <Play size={15} fill="currentColor" />}{busy ? `계산 중 ${elapsed}초` : '최적화 실행'}</button></div></section>
          <input ref={importRef} type="file" accept=".json,application/json" className="hidden-input" aria-label="JSON 시나리오 파일" onChange={e => importJSON(e.target.files[0])} />
          {uploadOpen && <section className="upload-panel panel"><div><h3>수요 Excel 불러오기</h3><p>지역·위도·경도·대형·소형·프리미엄 헤더를 자동 인식합니다. 인구는 선택 열입니다.</p></div><div className="upload-fields"><label className="field"><span>시트 이름 (선택)</span><input aria-label="업로드 시트 이름" value={sheet} onChange={e => setSheet(e.target.value)} placeholder="자동 인식" disabled={busy} /></label><label className="field"><span>컬럼 매핑 JSON (선택)</span><input aria-label="업로드 컬럼 매핑" value={mapping} onChange={e => setMapping(e.target.value)} placeholder={'{"id":"지역명","premium":"프리미엄"}'} disabled={busy} /></label><label className="upload-file button"><Upload size={16} />XLSX 파일 선택<input ref={uploadRef} type="file" accept=".xlsx" disabled={busy} aria-label="Excel 수요 파일" onChange={e => uploadExcel(e.target.files[0])} /></label></div></section>}
          <div className="statistics-heading"><h2>Overall Statistics <span>일별 네트워크 지표</span></h2><div><span className="data-count">원본 {fmt(inputUnits)}개 · {fmt(inputVolume, 1)} CBM/일</span>{currentPeriod && <label className="period-select">조회 기간<select aria-label="결과 조회 기간" value={periodIndex} onChange={e => setPeriodIndex(+e.target.value)}>{result.periods.map((p, i) => <option key={i} value={i}>{p.name} · {p.days}일</option>)}</select></label>}</div></div>
          <Statistics result={result} period={currentPeriod} busy={busy} />
          <div className="analysis-layout"><Settings scenario={scenario} edit={edit} selected={selected} onSelect={setSelected} onFacility={facilityPatch} deleteDC={deleteDC} addMode={addMode} setAddMode={setAddMode} result={result} busy={busy} defaults={defaults} /><div className="center-column"><NetworkMap scenario={scenario} result={result} period={currentPeriod} selected={selected} onSelect={setSelected} onFacility={facilityPatch} addMode={addMode} setAddMode={setAddMode} addDC={addDC} busy={busy} /><DetailTable scenario={scenario} result={result} period={currentPeriod} /></div><ResultPanel result={result} period={currentPeriod} scenario={scenario} busy={busy} onExport={exportResult} /></div>
          <footer className="workspace-footer"><span>내일의집 Network Lab <b>·</b> 정적 네트워크 설계</span><span>직선거리 기반 · 일평균 수요 · 패널티 허용 시 경제적 미충족 가능</span><button className="text-button" disabled={busy} onClick={loadDefault}><RotateCcw size={12} />원본 시나리오 복원</button></footer>
          {showSaved && <Scenarios entries={saved} scenario={scenario} onClose={() => setShowSaved(false)} onSave={saveCurrent} onLoad={loadEntry} onDuplicate={duplicate} onDelete={id => persist(saved.filter(e => e.id !== id))} />}
        </>}
      </main>
    </div>
  </div>;
}
