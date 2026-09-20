import React, {useEffect, useMemo, useState} from 'react';
import L from 'leaflet';
import {MapContainer, TileLayer, CircleMarker, Circle, Marker, Polyline, Popup, Tooltip, useMap, useMapEvents} from 'react-leaflet';
import {LocateFixed, Layers, Plus, MousePointer2, MapPin} from 'lucide-react';
import {fmt, cbm, total} from './utils.js';

const hasCoords = p => typeof p.lat === 'number' && Number.isFinite(p.lat) && Math.abs(p.lat) <= 90 && typeof p.lon === 'number' && Number.isFinite(p.lon) && Math.abs(p.lon) <= 180;
function Events({scenario, fit, addMode, addDC}) {
  const map = useMapEvents({click: e => { if (addMode) addDC(e.latlng.lat, e.latlng.lng); }});
  const coordinatesSignature = scenario.customers.map(c => `${c.lat},${c.lon}`).join(';');
  useEffect(() => { const points = [...scenario.customers, ...scenario.facilities].filter(hasCoords).map(x => [x.lat, x.lon]); if (points.length) map.fitBounds(points, {padding: [28, 28], maxZoom: 11}); }, [fit, coordinatesSignature, map]);
  useEffect(() => { const observer = new ResizeObserver(() => map.invalidateSize()); observer.observe(map.getContainer()); return () => observer.disconnect(); }, [map]);
  return null;
}
function Focus({facility}) { const map = useMap(); useEffect(() => {if (facility && hasCoords(facility)) map.panTo([facility.lat, facility.lon]);}, [facility?.id, map]); return null; }
export default function NetworkMap({scenario, result, period, selected, onSelect, onFacility, addMode, setAddMode, addDC, busy}) {
  const [fit, setFit] = useState(0);
  const [layers, setLayers] = useState({demand: true, premium: true, facilities: true, connections: true});
  const [layerPanel, setLayerPanel] = useState(false);
  const [tileError, setTileError] = useState(false);
  const opened = new Set(result?.open_facilities || []);
  const customers = useMemo(() => Object.fromEntries(scenario.customers.map(c => [c.id, c])), [scenario.customers]);
  const facilities = useMemo(() => Object.fromEntries(scenario.facilities.map(c => [c.id, c])), [scenario.facilities]);
  const current = facilities[selected];
  const radius = scenario.constraints.find(c => c.enabled && c.type === 'premium_distance' && !c.customer_id)?.value;
  const multiplier = period?.demand_multiplier ?? scenario.parameters.demand_multiplier * scenario.parameters.periods[0].demand_multiplier;
  return <section className={`map-panel ${addMode ? 'map-adding' : ''}`} aria-label="물류 네트워크 지도">
    <div className="map-heading"><div><span className="eyebrow">NETWORK EXPLORER</span><h2>수도권 물류 네트워크 <span>{scenario.customers.length} 수요지역</span></h2></div><div className="map-actions"><button className={addMode ? 'button active' : 'button'} disabled={busy || scenario.facilities.length >= 50} onClick={() => setAddMode(!addMode)} aria-pressed={addMode}><Plus size={15} />{addMode ? '추가 모드 종료' : '지도에서 DC 추가'}</button></div></div>
    <div className="map-body">
      <MapContainer center={[37.53, 127.04]} zoom={9} zoomControl={true} scrollWheelZoom={true} className="network-map">
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' eventHandlers={{tileerror: () => setTileError(true)}} />
        <Events scenario={scenario} fit={fit} addMode={addMode && !busy} addDC={addDC} />
        <Focus facility={current} />
        {current && hasCoords(current) && radius > 0 && <Circle center={[current.lat, current.lon]} radius={radius * 1000} pathOptions={{color: '#ce9752', weight: 1, dashArray: '5 6', fillOpacity: .025, interactive: false}} />}
        {layers.connections && period?.assignments.map(a => {
          const c = customers[a.customer_id], f = facilities[a.facility_id]; if (!c || !f || !hasCoords(c) || !hasCoords(f) || !total(a.quantities)) return null;
          return <Polyline key={a.customer_id} positions={[[f.lat, f.lon], [c.lat, c.lon]]} pathOptions={{color: a.quantities.premium ? '#a8793e' : '#267564', opacity: .5, weight: Math.min(6, 1 + cbm(a.quantities) / 65)}}><Tooltip>{f.name} → {c.name}<br />{fmt(total(a.quantities))}개 · 편도 {fmt(a.distance_km, 1)}km</Tooltip></Polyline>;
        })}
        {scenario.customers.filter(hasCoords).map(c => <React.Fragment key={c.id}>
          {layers.premium && c.demand.premium > 0 && <CircleMarker center={[c.lat, c.lon]} radius={Math.max(6, Math.min(13, 5 + Math.sqrt(c.demand.premium) / 3))} pathOptions={{color: '#d69b50', weight: 1.2, fillColor: '#d69b50', fillOpacity: .12, interactive: false}} />}
          {layers.demand && <CircleMarker center={[c.lat, c.lon]} radius={Math.max(3, Math.min(7, 2 + Math.sqrt(total(c.demand)) / 9))} pathOptions={{color: '#fff', weight: 1, fillColor: '#677f78', fillOpacity: .9}}><Tooltip>{c.name} · 기준 {fmt(total(c.demand))}개</Tooltip><Popup><div className="map-popup"><small>고정 수요지역</small><h3>{c.name}</h3><p>인구 {fmt(c.population)}명</p>{[['large', '대형'], ['small', '소형'], ['premium', '프리미엄']].map(([key, name]) => <div className="popup-row" key={key}><span>{name}</span><strong>{fmt(Math.floor(c.demand[key] * multiplier + .5))}개</strong></div>)}<small>적용 배수 {fmt(multiplier, 3)} · {fmt(c.lat, 4)}, {fmt(c.lon, 4)}</small></div></Popup></CircleMarker>}
        </React.Fragment>)}
        {layers.facilities && scenario.facilities.filter(hasCoords).map((f, i) => {
          const active = opened.has(f.id), isSelected = f.id === selected;
          const icon = L.divIcon({className: '', html: `<div class="dc-marker ${active ? 'opened' : ''} ${isSelected ? 'selected' : ''} ${!f.enabled ? 'disabled' : ''}"><span>${String(i + 1).padStart(2, '0')}</span></div>`, iconSize: [29, 35], iconAnchor: [14, 32]});
          return <Marker key={f.id} position={[f.lat, f.lon]} icon={icon} draggable={!busy} eventHandlers={{click: () => {onSelect(f.id); setAddMode(false);}, dragend: e => {const p = e.target.getLatLng(); onFacility(f.id, {lat: +p.lat.toFixed(6), lon: +p.lng.toFixed(6)}); onSelect(f.id);}}}><Tooltip direction="top" offset={[0, -25]}>{f.name} · {active ? '개설' : f.enabled ? '후보' : '비활성'}</Tooltip></Marker>;
        })}
      </MapContainer>
      <div className="map-tools"><button className="icon-button" aria-label="전체 네트워크 보기" title="전체 네트워크 보기" onClick={() => setFit(x => x + 1)}><LocateFixed size={19} /></button><button className={`icon-button ${layerPanel ? 'active' : ''}`} aria-label="지도 레이어 설정" aria-expanded={layerPanel} title="레이어 설정" onClick={() => setLayerPanel(!layerPanel)}><Layers size={19} /></button>{layerPanel && <div className="layer-panel">{[['demand', '수요지역'], ['premium', '프리미엄 수요'], ['facilities', 'DC 후보 / 개설'], ['connections', '배송 연결선']].map(([key, label]) => <label key={key}><input type="checkbox" checked={layers[key]} onChange={e => setLayers({...layers, [key]: e.target.checked})} />{label}</label>)}</div>}</div>
      {addMode && <div className="map-instruction"><MousePointer2 size={15} />지도 위 원하는 위치를 클릭하세요</div>}
      <div className="map-legend"><span><i className="legend-dot" />수요지역</span><span><i className="legend-dot premium" />프리미엄</span><span><i className="legend-square" />DC 후보</span><span><i className="legend-square open" />개설 DC</span></div>
    </div>
    <div className="map-footer"><span><MapPin size={12} />Haversine 직선거리 · 배송선은 실제 도로 경로가 아닙니다</span><span>{tileError ? '배경 지도 연결 지연 · 좌표 분석은 사용 가능' : 'DC 마커를 드래그하여 위치 조정'}</span></div>
  </section>;
}
