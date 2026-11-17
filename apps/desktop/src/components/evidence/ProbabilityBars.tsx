import type { CSSProperties } from "react";
import type { Probabilities } from "../../rpc";
import { formatProbability } from "../../app/format";
import { today } from "../../i18n/zh-CN/today";

export function ProbabilityBars({ probabilities }: { probabilities: Probabilities }) {
  return <ul className="c-barlist" aria-label={today.probabilityList}>
    {(Object.keys(today.probabilities) as (keyof Probabilities)[]).map(key => {
      const value = probabilities[key];
      return <li className="c-barlist__row" key={key}>
        <span className="c-barlist__label">{today.probabilities[key]}</span>
        <span className="c-barlist__track" aria-hidden="true"><span className="c-barlist__fill"
          style={{ "--w": `${value !== null && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) * 100 : 0}%` } as CSSProperties} /></span>
        <span className={`c-barlist__value${value === null ? " is-na" : ""}`}>{value === null ? today.noKillCondition : formatProbability(value)}</span>
      </li>;
    })}
  </ul>;
}
