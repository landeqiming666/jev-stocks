import { type KeyboardEvent } from "react";
import { Button, StatusTag, Table } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import type { PaperOrder, Position } from "../../rpc";
import { fixed, formatDecimal, integerText, moneyText } from "./validation";

export const TABS = ["pending", "fills", "positions", "history"] as const;
export type Tab = typeof TABS[number];
const tones = { pending: "info", filled: "ok", rejected: "danger", cancelled: "none" } as const;
export function OrdersTable({ tab, orders, positions, busy, highlight, onTab, onCancel }: {
  tab: Tab; orders: PaperOrder[]; positions: Position[]; busy: boolean; highlight?: string | null;
  onTab: (tab: Tab) => void; onCancel: (orderId: string) => Promise<unknown>;
}) {
  const sorted = [...orders].sort((a, b) => b.createdClockDate.localeCompare(a.createdClockDate) || b.orderId.localeCompare(a.orderId));
  const filtered = tab === "pending" ? sorted.filter(order => order.status === "pending") : sorted;
  const fills = orders.flatMap(order => order.fills.map(fill => ({ order, fill }))).sort((a, b) => b.fill.filledOn.localeCompare(a.fill.filledOn) || b.fill.fillId.localeCompare(a.fill.fillId));
  const sortedPositions = [...positions].filter(position => position.quantity > 0).sort((a, b) => fixed(a.marketValue, 4) > fixed(b.marketValue, 4) ? -1 : fixed(a.marketValue, 4) < fixed(b.marketValue, 4) ? 1 : 0);
  const headings = tab === "fills" ? [t.filledDate, t.instrument, t.direction, t.quantity, t.price, t.amount, t.fee] :
    tab === "positions" ? [t.instrument, t.quantity, t.sellable, t.cost, t.close, t.marketValue, t.pnl] :
    [t.instrument, t.direction, t.quantity, t.type, t.price, t.status, t.date, ""];
  const empty = tab === "fills" ? !fills.length : tab === "positions" ? !sortedPositions.length : !filtered.length;
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? 3 : (index + (event.key === "ArrowRight" ? 1 : 3)) % 4;
    onTab(TABS[next]!); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
  }
  return <div className="c-card c-card--flush"><div className="c-card__pad-x"><div className="c-tabs" role="tablist" aria-label={t.records}>
    {TABS.map((value, index) => <button type="button" key={value} id={`tab-${value}`} className={`c-tabs__tab${value === tab ? " is-active" : ""}`}
      role="tab" tabIndex={value === tab ? 0 : -1} aria-selected={value === tab} aria-controls="orders-panel"
      onClick={() => onTab(value)} onKeyDown={event => move(event, index)}>{t[value]}</button>)}
  </div></div><div className="c-card__pad" id="orders-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0}>
    {empty ? <p className="u-muted">{tab === "pending" ? t.emptyPending : tab === "fills" ? t.emptyFills : tab === "positions" ? t.emptyPositions : t.emptyHistory}</p> :
      <Table label={t[tab]}><thead><tr>{headings.map((heading, index) => <th key={index} scope="col" className={index > 1 && index < 5 ? "c-table__num" : ""}>{heading}</th>)}</tr></thead>
        <tbody>{tab === "fills" ? fills.map(({ order, fill }) => <tr key={fill.fillId}>
          <td className="u-mono">{fill.filledOn}</td><td className="u-mono"><strong>{order.instrument.symbol}</strong></td><td>{t[order.side]}</td>
          <td className="c-table__num">{integerText(fill.quantity)}</td><td className="c-table__num">{formatDecimal(fill.price, 4)}</td>
          <td className="c-table__num">{moneyText(fill.amount)}</td><td className="c-table__num">{moneyText(fill.fee)}</td>
        </tr>) : tab === "positions" ? sortedPositions.map(position => <tr key={position.instrument.instrumentId}>
          <td className="u-mono"><strong>{position.instrument.symbol}</strong></td><td className="c-table__num">{integerText(position.quantity)}</td>
          <td className="c-table__num">{integerText(Math.max(0, position.sellableQuantity - orders.filter(order => order.instrument.instrumentId === position.instrument.instrumentId && order.side === "sell" && order.status === "pending").reduce((sum, order) => sum + order.quantity, 0)))}</td>
          <td className="c-table__num">{formatDecimal(position.avgCost, 4)}</td><td className="c-table__num">{formatDecimal(String(position.lastClose), 4)}</td>
          <td className="c-table__num">{moneyText(position.marketValue)}</td><td className={`c-table__num ${fixed(position.unrealizedPnl, 4) >= 0n ? "u-up" : "u-down"}`}>
            {fixed(position.unrealizedPnl, 4) >= 0n ? "+" : ""}{moneyText(position.unrealizedPnl)} ({(position.unrealizedPnlPct * 100).toFixed(1)}%)</td>
        </tr>) : filtered.map(order => <tr key={order.orderId} data-order-id={order.orderId} className={highlight === order.orderId ? "is-selected" : ""}>
          <td className="u-mono"><strong>{order.instrument.symbol}</strong></td><td>{t[order.side]}</td><td className="c-table__num">{integerText(order.quantity)}</td>
          <td>{t.marketOpen}</td><td className="c-table__num" title={order.estimate ? `${t.estimateAmount} ${moneyText(order.estimate.amount)} · ${t.estimateFee} ${moneyText(order.estimate.fee)}` : undefined}>
            {order.fills[0] ? formatDecimal(order.fills[0].price, 4) : order.estimate ? `≈ ${formatDecimal(order.estimate.price, 4)}` : "—"}</td>
          <td><StatusTag tone={tones[order.status]}>{t.statuses[order.status]}</StatusTag>
            {order.rejectReason && <div className="p-trading__reject">{order.rejectReason.message}</div>}
            {highlight === order.orderId && <div className="c-note">{t.orderId} {order.orderId}</div>}</td>
          <td className="c-table__num">{order.createdClockDate}</td><td>{order.status === "pending" && <Button variant="text" disabled={busy}
            onClick={() => { void onCancel(order.orderId).catch(() => {}); }}>{t.cancelOrder}</Button>}</td>
        </tr>)}</tbody></Table>}
  </div></div>;
}
