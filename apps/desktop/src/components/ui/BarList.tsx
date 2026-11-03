import { forwardRef, useEffect, type CSSProperties } from "react";
import { common } from "../../i18n/zh-CN/common";

export interface BarListProps {
  items: { label: string; value: number }[];
  label: string;
}

export const BarList = forwardRef<HTMLUListElement, BarListProps>(function BarList({ items, label }, ref) {
  useEffect(() => {
    if (import.meta.env.DEV && items.some(item => !Number.isFinite(item.value))) console.warn("BarList received a nonfinite value");
  }, [items]);
  return <ul ref={ref} className="c-barlist" aria-label={label}>
    {items.map((item, index) => {
      const fraction = Number.isFinite(item.value) ? Math.max(0, Math.min(1, item.value)) : 0;
      return <li key={index} className="c-barlist__row">
        <span className="c-barlist__label">{item.label}</span>
        <span className="c-barlist__track"><span className="c-barlist__fill"
          style={{ "--w": `${Math.round(fraction * 100)}%` } as CSSProperties} /></span>
        <span className="c-barlist__value">{Number.isFinite(item.value) ? (fraction * 100).toFixed(1) : "0"}{common.chartUnits.percent}</span>
      </li>;
    })}
  </ul>;
});
