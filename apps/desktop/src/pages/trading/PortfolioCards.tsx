import { Skeleton } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import type { Portfolio } from "../../rpc";
import { moneyText, sumMoney } from "./validation";

export function PortfolioCards({ portfolio }: { portfolio: Portfolio | null }) {
  const metrics = portfolio ? [
    [t.cash, moneyText(portfolio.cash), `${t.available} ${moneyText(portfolio.availableCash)}`],
    [t.reserved, moneyText(portfolio.reservedCash), t.frozenCount(portfolio.pendingOrders)],
    [t.marketValue, moneyText(sumMoney(portfolio.positions.map(position => position.marketValue))), ""],
    [t.equity, moneyText(portfolio.equity), t.asOf(portfolio.asOf)],
  ] : [t.cash, t.reserved, t.marketValue, t.equity].map(label => [label, "", ""]);
  return <div className="c-metrics" aria-label={t.metrics}>
    {metrics.map(([label, value, sub]) => <div className="c-metric" key={label}>
      <div className="c-metric__label">{label}</div>
      <div className="c-metric__value" title={value}>{portfolio ? value : <Skeleton rows={1} />}</div>
      <div className="c-metric__hint">{sub || "\u00a0"}</div>
    </div>)}
  </div>;
}
