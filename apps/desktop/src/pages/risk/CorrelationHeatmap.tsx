import { useId, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { RiskResult } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";
import { cellTitle, number } from "./format";
import { RiskTable } from "./RiskTable";

export const CELL = 56, GAP = 2, MAX_MIX = 70;
export function CorrelationHeatmap({ result, table }: { result: RiskResult; table: boolean }) {
  const { symbols, matrix } = result.correlation;
  const n = symbols.length, step = CELL + GAP, left = 64, top = 28;
  const id = useId().replace(/:/g, "");
  const [selected, select] = useState<[number, number]>([0, 0]);
  const [tip, showTip] = useState<[number, number] | null>(null);
  const tooltip = tip && matrix[tip[0]]?.[tip[1]] !== undefined ?
    cellTitle(symbols[tip[0]]!, symbols[tip[1]]!, matrix[tip[0]]![tip[1]]!) : null;
  const entry = selected[0] < n && selected[1] < n ? selected : [0, 0];
  function move(event: KeyboardEvent<SVGGElement>, i: number, j: number) {
    if (event.key === "Escape") { showTip(null); return; }
    let row = i, col = j;
    switch (event.key) {
      case "ArrowRight": col = (j + 1) % n; break;
      case "ArrowLeft": col = (j + n - 1) % n; break;
      case "ArrowDown": row = (i + 1) % n; break;
      case "ArrowUp": row = (i + n - 1) % n; break;
      case "Home": col = 0; break;
      case "End": col = n - 1; break;
      default: return;
    }
    event.preventDefault();
    select([row, col]);
    event.currentTarget.ownerSVGElement?.querySelector<SVGGElement>(`[data-row="${row}"][data-col="${col}"]`)?.focus();
  }
  if (table) return <RiskTable result={result} />;
  return <div className="p-risk__heat">
    <div className="p-risk__chart-scroll">
      <svg className="c-heatmap" role="img" aria-label={risk.heatmapLabel(n)} aria-describedby={`${id}-help`}
        viewBox={`0 0 ${left + n * step} ${top + n * step}`} width={left + n * step}>
        <defs><pattern id={`${id}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse">
          <path d="M-1 1L1-1M0 6L6 0M5 7L7 5" className="c-heatmap__hatch" />
        </pattern></defs>
        {symbols.map((symbol, i) => <g key={i}>
          <text className="c-heatmap__label" x={left + i * step + CELL / 2} y={top - 10} textAnchor="middle">{symbol}</text>
          <text className="c-heatmap__label" x={left - 8} y={top + i * step + CELL / 2 + 4} textAnchor="end">{symbol}</text>
        </g>)}
        {matrix.map((row, i) => row.map((value, j) => {
          const x = left + j * step, y = top + i * step;
          const title = cellTitle(symbols[i]!, symbols[j]!, value);
          const kind = value === null ? "is-na" : i === j ? "is-diag" : value < 0 ? "is-neg" : "is-pos";
          return <g key={`${i}-${j}`} className={`c-heatmap__cell ${kind}`} data-row={i} data-col={j}
            tabIndex={entry[0] === i && entry[1] === j ? 0 : -1} aria-label={title}
            aria-describedby={tooltip === title ? `${id}-tooltip` : undefined}
            onFocus={() => { select([i, j]); showTip([i, j]); }} onBlur={() => showTip(null)}
            onMouseEnter={() => showTip([i, j])} onMouseLeave={() => showTip(null)}
            onKeyDown={event => move(event, i, j)}>
            <title>{title}</title>
            <rect className="c-heatmap__rect" x={x} y={y} width={CELL} height={CELL} rx="4"
              style={{ "--k": `${value === null ? 0 : Math.round(Math.abs(value) * MAX_MIX)}%` } as CSSProperties} />
            {value === null && <rect className="c-heatmap__null" x={x} y={y} width={CELL} height={CELL} rx="4"
              fill={`url(#${id}-hatch)`} />}
            <text className="c-heatmap__value" x={x + CELL / 2} y={y + CELL / 2}>{number(value)}</text>
          </g>;
        }))}
      </svg>
    </div>
    <div className="c-legend" aria-hidden="true"><span>−1</span><span className="c-legend__bar" /><span>0</span><span>+1</span></div>
    <p className="c-note" id={`${id}-help`}>{risk.heatHelp}</p>
    {matrix.some(row => row.includes(null)) && <p className="c-note">{risk.nullNote}</p>}
    <div className="p-risk__tooltip-slot">{tooltip && <p role="tooltip" id={`${id}-tooltip`}>{tooltip}</p>}</div>
  </div>;
}
