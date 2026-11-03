import type { RiskResult } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";
import { number, percent, topWeight } from "./format";

export function MetricCards({ result }: { result: RiskResult }) {
  const items = [
    { label: risk.vol, value: percent(result.annualizedVol) },
    { label: risk.drawdown, value: percent(result.maxDrawdown), hint: risk.drawdownHint },
    { label: risk.effective, value: number(result.effectiveHoldings), hint: risk.effectiveHint },
    { label: risk.top, value: percent(topWeight(result)), hint: result.topWeights.slice(0, 3)
      .map(item => `${item.symbol} ${percent(item.weight)}`).join(" · ") },
  ];
  return <div className="c-metrics">{items.map(item => <div className="c-metric" key={item.label}>
    <div className="c-metric__label">{item.label}</div>
    <div className="c-metric__value">{item.value}</div>
    {item.hint && <div className="c-metric__hint">{item.hint}</div>}
  </div>)}</div>;
}
