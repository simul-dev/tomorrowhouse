import React, {useId, useState} from 'react';
import { RotateCcw } from 'lucide-react';
export function Field({label, value, onChange, min, max, step = 'any', hint, type = 'number', nullable = false, disabled = false}) {
  return <label className="field"><span>{label}</span><input aria-label={label} type={type} min={min} max={max} step={step} value={value ?? ''} disabled={disabled} onChange={e => onChange(type === 'number' ? (e.target.value === '' ? (nullable ? null : '') : Number(e.target.value)) : e.target.value)} /><small>{hint}</small></label>;
}
export function Select({label, value, onChange, children}) { return <label className="field"><span>{label}</span><select aria-label={label} value={value ?? ''} onChange={e => onChange(e.target.value)}>{children}</select></label>; }
export function Toggle({label, checked, onChange, hint}) { return <label className="toggle-row"><span><b>{label}</b>{hint && <small>{hint}</small>}</span><input aria-label={label} type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} /><i aria-hidden="true" /></label>; }
export function Section({eyebrow, title, children, action}) { return <section className="form-section"><div className="section-title"><div>{eyebrow && <small>{eyebrow}</small>}<h3>{title}</h3></div>{action}</div>{children}</section>; }
export function Empty({icon: Icon, title, children}) { return <div className="empty-state">{Icon && <div className="empty-icon"><Icon size={26} strokeWidth={1.5} /></div>}<h3>{title}</h3><p>{children}</p></div>; }
export function Reset({onClick, label = '기본값 복원'}) { return <button type="button" className="icon-button" aria-label={label} title={label} onClick={onClick}><RotateCcw size={15} /></button>; }
export function Hint({text, label, children, className = ''}) {
  const id = useId();
  const [pinned, setPinned] = useState(false);
  return <span className={`hint ${className} ${pinned ? 'pinned' : ''}`}>
    <button type="button" className="hint-trigger" aria-label={label} aria-describedby={id} aria-expanded={pinned} onClick={() => setPinned(open => !open)} onBlur={() => setPinned(false)}>{children}</button>
    <span className="hint-bubble" role="tooltip" id={id}>{text}</span>
  </span>;
}
