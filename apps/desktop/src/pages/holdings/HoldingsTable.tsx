import { Fragment, type ReactNode } from "react";
import { formatMoney, formatPercent } from "../../app/format";
import { Button, StatusTag, Table } from "../../components/ui";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import type { Holding } from "../../rpc/generated/types";
import { formatQuantity, isWatch } from "./validation";

export function HoldingsTable({ items, expandedId, onToggle, detail }: {
  items: Holding[]; expandedId: string | null; onToggle: (id: string) => void; detail: (h: Holding) => ReactNode;
}) {
  return <div className="c-card c-card--flush"><Table label={text.title}>
    <thead><tr>{text.columns.map((label, i) => <th key={label} scope="col" className={i > 0 && i < 7 ? "c-table__num" : undefined}>{label}</th>)}</tr></thead>
    <tbody>{items.map(h => {
      const i = h.instrument, open = expandedId === i.instrumentId, watch = isWatch(h.quantity);
      const dc = h.dayChangePct, tone = h.status === "guarded" ? "ok" : h.status === "attention" ? "warn" : "none";
      return <Fragment key={i.instrumentId}>
        <tr id={`holding-${i.symbol}`} className={`c-table__click${open ? " is-selected" : ""}`} tabIndex={0}
          aria-expanded={open} aria-controls={open ? `detail-${i.symbol}` : undefined}
          onClick={() => onToggle(i.instrumentId)} onKeyDown={e => {
            if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onToggle(i.instrumentId); }
          }}>
          <td><div className="c-table__symbol"><Button variant="icon" icon={open ? "chevron-down" : "chevron-right"}
            aria-label={open ? text.collapse(i.symbol) : text.expand(i.symbol)} aria-expanded={open}
            aria-controls={open ? `detail-${i.symbol}` : undefined} onClick={e => { e.stopPropagation(); onToggle(i.instrumentId); }} />
            <div className="c-table__symbol-text"><span><strong className="u-mono">{i.symbol}</strong> <span className="u-text-2">{i.name}</span></span>
              <span className="c-table__sub">{i.nameZh} · {i.exchange}</span></div></div></td>
          <td className="c-table__num">{watch ? text.watch : formatQuantity(h.quantity)}</td>
          <td className="c-table__num">{h.avgCost !== null ? formatMoney(h.avgCost) : "—"}</td>
          <td className="c-table__num" title={h.lastCloseDate ?? undefined}>{h.lastClose !== null ? formatMoney(String(h.lastClose)) : "—"}</td>
          <td className={`c-table__num ${dc !== null && dc > 0 ? "u-up" : dc !== null && dc < 0 ? "u-down" : ""}`}>{dc === null ? "—" : formatPercent(dc, 1, true)}</td>
          <td className="c-table__num">{watch || h.marketValue === null ? "—" : formatMoney(h.marketValue)}</td>
          <td className="c-table__num">{text.count(h.thesisCount)}</td>
          <td><StatusTag tone={tone}>{text.status[h.status]}</StatusTag>{h.pendingCount > 0 && <span className="u-small u-muted"> {text.count(h.pendingCount)}</span>}</td>
        </tr>
        {open && <tr className="c-table__detail" id={`detail-${i.symbol}`}><td colSpan={8}>{detail(h)}</td></tr>}
      </Fragment>;
    })}</tbody>
  </Table></div>;
}
