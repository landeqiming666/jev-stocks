import type { CSSProperties } from "react";
import type { RiskResult } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";
import { number, percent } from "./format";

export const TOP_LOADINGS = 5;
export function SvdPanel({ result }: { result: RiskResult }) {
  const single = result.correlation.symbols.length < 2;
  const loadings = [...result.svd.loadings].sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, TOP_LOADINGS);
  return <section className="c-card p-risk__svd" aria-labelledby="risk-svd-title">
    <h2 className="c-card__title" id="risk-svd-title">{risk.svd}</h2>
    <p className="c-note p-risk__svd-note">{risk.svdNote}</p>
    {single ? <p className="u-text-2">{risk.singleSvd}</p> : !result.svd.explained.length ?
      <p className="u-text-2">{risk.zeroSvd}</p> : <>
        <div role="img" aria-label={`${risk.explained}：${result.svd.explained.slice(0, 5)
          .map((value, i) => `${risk.component(i + 1)} ${percent(value)}`).join("，")}`}>
          <ul className="c-barlist" aria-label={risk.explained}>
            {result.svd.explained.slice(0, 5).map((value, i) => <li className="c-barlist__row" key={i}>
              <span className="c-barlist__label">{risk.component(i + 1)}</span>
              <span className="c-barlist__track"><span className="c-barlist__fill"
                style={{ "--w": `${value * 100}%` } as CSSProperties} /></span>
              <span className="c-barlist__value" title={String(value)}>{percent(value)}</span>
            </li>)}
          </ul>
        </div>
        <h3 className="c-card__subtitle p-risk__loadings-title">{risk.loadings}</h3>
        <ul className="p-risk__loadings">{loadings.map((item, i) => <li key={i}>
          <span className="u-mono">{item.symbol}</span><span className="u-mono" title={String(item.value)}>{number(item.value)}</span>
        </li>)}</ul>
      </>}
    <dl className="p-risk__conditions" aria-label={risk.conditions}>
      <div><dt>{risk.raw}</dt><dd className="u-mono">{result.conditionNumberRaw === null ? risk.conditionNull : number(result.conditionNumberRaw)}</dd></div>
      <div><dt>{risk.shrunk}</dt><dd className="u-mono">{result.conditionNumberShrunk === null ? risk.conditionNull : number(result.conditionNumberShrunk)}</dd></div>
    </dl>
  </section>;
}
