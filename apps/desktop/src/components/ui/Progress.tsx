import { forwardRef, type CSSProperties } from "react";

export interface ProgressProps { value: number; max: number; label: string; }
export const Progress = forwardRef<HTMLDivElement, ProgressProps>(function Progress({ value, max, label }, ref) {
  const total = Number.isFinite(max) && max > 0 ? max : 0;
  const done = Number.isFinite(value) ? Math.max(0, Math.min(total, value)) : 0;
  const width = total > 0 ? Math.round(done / total * 1000) / 10 : 0;
  return <div ref={ref} className="c-progress">
    <div className="c-progress__label"><span>{label}</span><span className="u-mono">{done} / {total}</span></div>
    <div className="c-progress__track" role="progressbar" aria-label={label}
      aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-live="polite">
      <span className="c-progress__fill" style={{ "--w": `${width}%` } as CSSProperties} />
    </div>
  </div>;
});
