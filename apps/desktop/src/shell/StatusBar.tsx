import { common } from "../i18n/zh-CN";
import { formatDate, formatTime, formatTokens } from "../app/format";
import { useAppStore } from "../app/store";

export function StatusBar() {
  const asOf = useAppStore(state => state.dataAsOf);
  const scanned = useAppStore(state => state.lastSuccessfulScanAt);
  const budget = useAppStore(state => state.budget);
  const progress = useAppStore(state => state.scanProgress);
  return <footer className="l-status">
    <span>{common.dataAsOf} <span className="u-mono">{asOf ? formatDate(asOf) : common.unknown}</span></span>
    <span className="l-status__sep" aria-hidden="true">·</span>
    <span>{common.lastSuccessfulScan} <span className="u-mono">{scanned ? formatTime(scanned) : common.unknown}</span></span>
    <span className="l-status__sep" aria-hidden="true">·</span>
    <span>{common.todayTokens} <span className="u-mono">{budget ? `${formatTokens(budget.usedTokens)} / ${formatTokens(budget.limitTokens)} tokens` : common.notReady}</span></span>
    <span className="l-status__spacer" />
    {progress && <span role="status">{common.scanning} {progress.done} / {progress.total}</span>}
    <span className="l-status__disclaimer">{common.disclaimer}</span>
  </footer>;
}
