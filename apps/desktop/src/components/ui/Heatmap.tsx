import { forwardRef, useId, type CSSProperties } from "react";
import { common } from "../../i18n/zh-CN/common";
import { EmptyState } from "./EmptyState";

export interface HeatmapProps {
  symbols: string[];
  matrix: (number | null)[][];
  label: string;
}

export const HEAT_CELL = 56;
export const HEAT_GAP = 2;
export const HEAT_MAX_MIX = 70;

export const Heatmap = forwardRef<SVGSVGElement, HeatmapProps>(function Heatmap({ symbols, matrix, label }, ref) {
  const patternId = `hatch-${useId().replace(/:/g, "")}`;
  const n = symbols.length, cell = HEAT_CELL, step = cell + HEAT_GAP, left = 56, top = 28;
  if (matrix.length !== n || Array.from(matrix).some(row => !Array.isArray(row) || row.length !== n || Array.from(row).some(value =>
    value !== null && (!Number.isFinite(value) || value < -1 || value > 1)))) {
    return <EmptyState title={common.chartInvalid} />;
  }
  if (!n) return <EmptyState title={common.chartEmpty} />;
  return <svg ref={ref} className="c-heatmap" role="img" aria-label={label}
    viewBox={`0 0 ${left + n * step} ${top + n * step}`}>
    <defs><pattern id={patternId} width="6" height="6" patternUnits="userSpaceOnUse">
      <path d="M-1 1L1-1M0 6L6 0M5 7L7 5" className="c-heatmap__hatch" />
    </pattern></defs>
    {symbols.map((symbol, index) => <g key={`${symbol}-${index}`}>
      <text className="c-heatmap__label" x={left + index * step + cell / 2} y={top - 10} textAnchor="middle">{symbol}</text>
      <text className="c-heatmap__label" x={left - 8} y={top + index * step + cell / 2 + 4} textAnchor="end">{symbol}</text>
    </g>)}
    {matrix.map((row, i) => row.map((value, j) => {
      const x = left + j * step, y = top + i * step;
      const kind = value === null ? "is-na" : i === j ? "is-diag" : value < 0 ? "is-neg" : "is-pos";
      return <g key={`${i}-${j}`} className={`c-heatmap__cell ${kind}`} data-row={i} data-col={j}>
        <title>{common.chartCellTitle(symbols[i]!, symbols[j]!, value)}</title>
        <rect className="c-heatmap__rect" x={x} y={y} width={cell} height={cell} rx="4"
          style={{ "--k": `${Math.round(Math.abs(value ?? 0) * HEAT_MAX_MIX)}%` } as CSSProperties} />
        {value === null && <rect className="c-heatmap__null" x={x} y={y} width={cell} height={cell} rx="4" fill={`url(#${patternId})`} />}
        <text className="c-heatmap__value" x={x + cell / 2} y={y + cell / 2}>
          {value === null ? common.invalidValue : value.toFixed(2)}
        </text>
      </g>;
    }))}
  </svg>;
});
