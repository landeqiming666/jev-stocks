import { useState } from "react";
import { useAppStore } from "../../app/store";
import { PageFrame } from "../../shell/PageFrame";
import { Button, EmptyState } from "../../components/ui";
import "../../components/ui/components.css";
import { risk } from "../../i18n/zh-CN/risk";
import { useRisk } from "./useRisk";
import { RiskControls } from "./RiskControls";
import { MetricCards } from "./MetricCards";
import { CorrelationHeatmap } from "./CorrelationHeatmap";
import { SvdPanel } from "./SvdPanel";
import { unadjusted } from "./format";
import "./risk.css";

export default function RiskPage() {
  const client = useAppStore(state => state.client);
  const bootstrap = useAppStore(state => state.bootstrap);
  const ready = bootstrap.status === "ready";
  const { result, loading, error, window, setWindow, refresh, refreshPrices } = useRisk(client, ready);
  const [table, setTable] = useState(false);
  const errorTitle = error?.code === "DATA_INSUFFICIENT" && error.data.reason === "NO_HOLDINGS" ?
    risk.noHoldings : error?.message ?? risk.loadFailed;
  return <PageFrame><section className={`p-risk${loading ? " is-loading" : ""}`}
    data-ready={Boolean(ready && !loading && (result || error))} aria-busy={loading}>
    <header className="p-page__head"><div><h1 className="p-page__title">{risk.title}</h1>
      <p className="p-page__sub">{risk.scope}</p></div>
      <div className="p-page__actions">
        <Button disabled={!ready || loading} onClick={() => { void refresh(); }}>{risk.refresh}</Button>
        <Button icon="refresh-cw" disabled={!ready || loading} onClick={() => { void refreshPrices(); }}>{risk.refreshPrices}</Button>
      </div>
    </header>
    <RiskControls window={window} onWindow={setWindow} table={table} onTable={setTable} />
    <div className="p-risk__status" role="status" aria-live="polite">
      {!ready ? risk.waiting : loading ? result && result.window.label !== window ?
        risk.oldWindow(window, result.window.label) : risk.loading : error && result ? risk.notUpdated : null}
    </div>
    {error && result && <div className="p-risk__warnings" role="alert"><p>{errorTitle}</p></div>}
    {!result && error ? <EmptyState title={errorTitle} text={risk.insufficientHelp}
      action={<Button icon="refresh-cw" disabled={loading} onClick={() => { void refreshPrices(); }}>{risk.refreshPrices}</Button>} /> :
      !result ? <div aria-label={risk.loading} className="p-risk__skeleton">
        <div className="c-metrics">{Array.from({ length: 4 }, (_, i) => <div key={i} className="c-skeleton c-skeleton--card" />)}</div>
        <div className="p-risk__skeleton-grid">{Array.from({ length: 25 }, (_, i) => <div key={i} className="c-skeleton" />)}</div>
      </div> : <>
        {result.warnings.length > 0 && <aside className="p-risk__warnings" aria-label={risk.warnings}>
          <ul>{result.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
        </aside>}
        <MetricCards result={result} />
        <div className="p-grid-2 p-risk__body"><section className="c-card" aria-labelledby="risk-correlation-title">
          <h2 className="c-card__title" id="risk-correlation-title">{risk.correlation}</h2>
          {result.correlation.symbols.length < 2 ? <p className="u-text-2">{risk.single}</p> :
            <CorrelationHeatmap key={`${result.window.label}-${result.asOf}-${table}`} result={result} table={table} />}
        </section><SvdPanel result={result} /></div>
        <footer className="p-risk__foot">
          <p>{risk.data(result.window.label, result.window.observations, result.window.from, result.window.to)}</p>
          <p>{risk.latest(result.asOf)} · {unadjusted(result) ? risk.unadjusted : risk.adjusted}</p>
          {result.excluded.length > 0 && <p>{risk.excluded(result.excluded.map(item => `${item.symbol}（${item.reason}）`).join("、"))}</p>}
        </footer>
        <details className="p-risk__method" open><summary>{risk.methodTitle}</summary><p>{risk.method}</p></details>
      </>}
  </section></PageFrame>;
}
