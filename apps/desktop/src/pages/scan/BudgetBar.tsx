import type { CSSProperties } from "react";
import { Banner } from "../../components/ui/Banner";
import { scan } from "../../i18n/zh-CN/scan";
import { cost, number, time } from "./format";

export const BUDGET_WARN = 80;
export const BUDGET_DANGER = 100;
export function BudgetBar({ usedTokens, limitTokens, estCostUsd, resetAt }: {
  usedTokens: number; limitTokens: number; estCostUsd?: string | null; resetAt: string;
}) {
  const valid = Number.isSafeInteger(usedTokens) && usedTokens >= 0 && Number.isSafeInteger(limitTokens) && limitTokens > 0;
  const pct = valid ? usedTokens / limitTokens * 100 : 0;
  const tone = pct >= BUDGET_DANGER ? "danger" : pct >= BUDGET_WARN ? "warn" : "";
  return <div className={`c-card p-scan__budget${tone ? ` is-${tone}` : ""}`}>
    <div className="u-row u-row--between">
      <strong>{scan.budget}</strong>
      <span className="u-small u-muted">{scan.estimate} {cost(estCostUsd)} · {scan.reset} {time(resetAt)}</span>
    </div>
    <div className="c-progress">
      <div className="c-progress__label"><span>{pct >= 100 ? scan.budgetExhausted : scan.used}</span>
        <span className="u-mono">{number(usedTokens)} / {number(limitTokens)} tokens</span>
      </div>
      <div className="c-progress__track" role="progressbar" aria-label={scan.budget}
        aria-valuemin={0} aria-valuemax={valid ? limitTokens : undefined} aria-valuenow={valid ? Math.min(usedTokens, limitTokens) : undefined}>
        <span className="c-progress__fill" style={{ "--w": `${Math.min(100, pct)}%` } as CSSProperties} />
      </div>
    </div>
    {tone && <Banner tone={tone} text={pct >= 100 ? `${scan.budgetExhausted} · ${scan.reset} ${time(resetAt)}` : `${scan.budgetWarning} ${Math.floor(pct)}%`} />}
  </div>;
}
