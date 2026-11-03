import { Drawer } from "../../components/ui/Drawer";
import { Button } from "../../components/ui/Button";
import { StatusTag } from "../../components/ui/StatusTag";
import { Banner } from "../../components/ui/Banner";
import { scan } from "../../i18n/zh-CN/scan";
import type { RpcError, ScanBatch } from "../../rpc";
import type { RunDetail } from "./useScanRuns";
import { cost, duration, engine, number, time, tone } from "./format";

export const DETAIL_WIDTH = 400;
export function BatchRow({ batch, retrying, error, disabledReason, onRetry }: {
  batch: ScanBatch; retrying: boolean; error?: RpcError; disabledReason?: string; onRetry: (batchId: string) => Promise<void>;
}) {
  return <li className="c-card c-card--tight p-scan__batch" data-batch-id={batch.batchId}>
    <div className="u-row u-row--between"><strong className="u-mono">{batch.instrumentId.replace(/^us:/, "")}</strong>
      <StatusTag tone={tone[batch.status]}>{scan.statuses[batch.status]}</StatusTag></div>
    <p className="u-small u-text-2">{batch.eventTitle}</p>
    <p className="u-small u-muted">{scan.attempts} {number(batch.attempts)} {scan.times} · {number(batch.inputTokens)} tokens</p>
    <p className="u-small u-muted">{scan.columns[4]} {number(batch.passages)} · {scan.columns[5]} {number(batch.decisions)}</p>
    {batch.error && <p className="u-small u-danger"><span className="u-mono">{batch.error.code}</span> · {batch.error.message}</p>}
    {error && <p className="u-small u-danger" role="alert">{error.code} · {error.message}{error.code === "TIMEOUT" ? ` ${scan.retryTimeout}` : ""}</p>}
    {batch.status === "failed" && <Button icon="refresh-cw" loading={retrying} disabled={Boolean(disabledReason)}
      disabledReason={disabledReason} onClick={() => { void onRetry(batch.batchId); }}>{scan.retry}</Button>}
  </li>;
}
export function RunDetailDrawer({ runId, overlay, detail, loading, error, retrying, reconciling, retryErrors, disabledReason, onClose, onRetryBatch, onRefresh }: {
  runId: string | null; overlay: boolean; detail: RunDetail | null; loading: boolean; error: RpcError | null;
  retrying: string[]; reconciling: string[]; retryErrors: Record<string, RpcError>; disabledReason?: string;
  onClose: () => void; onRetryBatch: (batchId: string) => Promise<void>; onRefresh: () => Promise<void>;
}) {
  const run = detail?.run;
  const stats = run?.stats;
  const summary = run?.batchSummary;
  const rows = run && stats ? [
    [scan.window, `${time(run.windowStart)} ${scan.to} ${time(run.windowEnd)}`],
    [scan.columns[10], `${engine(run.engine)} · ${run.modelId}`],
    [scan.columns[2], `${number(stats.instruments)} (${number(stats.skippedNoThesis)} ${scan.skipped})`],
    [`${scan.columns[3]} / ${scan.columns[4]}`, `${number(stats.filings)} / ${number(stats.passages)}`],
    [scan.columns[5], `${number(stats.decisions)} (${scan.cached} ${number(stats.cachedDecisions)})`],
    [scan.columns[6], number(stats.requests)],
    [scan.tokensCost, `${number(stats.inputTokens)} / ${cost(stats.estCostUsd)}`],
    [scan.columns[9], duration(stats.durationMs)],
    [scan.batchSummary, summary ? `${scan.batches} ${number(summary.total)} · ${scan.statuses.succeeded} ${number(summary.succeeded)} · ${scan.statuses.failed} ${number(summary.failed)} · ${scan.pending} ${number(summary.pending)}` : "—"],
  ] : [];
  return <Drawer open={Boolean(runId)} titleId="scan-detail-title" overlay={overlay} onClose={onClose}>
    <header className="c-drawer__head"><h2 id="scan-detail-title" className="c-drawer__title u-grow" tabIndex={-1}>{scan.details}</h2>
      {run && <StatusTag tone={tone[run.status]}>{scan.statuses[run.status]}</StatusTag>}
      <Button variant="icon" icon="x" aria-label={scan.close} onClick={onClose} />
    </header>
    <div className="c-drawer__body" aria-busy={loading}>
      {loading && !detail && <p role="status">{scan.detailLoading}</p>}
      {error && <Banner tone="danger" text={`${error.code} · ${error.message}`} action={<Button onClick={() => { void onRefresh(); }}>{scan.retry}</Button>} />}
      {run && <>
        <section className="c-drawer__sec"><h3>{scan.rangeStats}</h3><dl className="c-kv">
          {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>{run.error && <Banner tone="warn" text={`${run.error.code} · ${run.error.message}`} />}</section>
        <section className="c-drawer__sec"><h3>{scan.listedBatches} ({number(detail.batches.length)})</h3>
          {!detail.batches.length ? <p className="u-muted">{scan.noBatches}</p> : <ul className="p-stack">
            {detail.batches.map(batch => <BatchRow key={batch.batchId} batch={batch} retrying={retrying.includes(batch.batchId)}
              error={retryErrors[batch.batchId]} disabledReason={disabledReason || (reconciling.includes(batch.batchId) ? scan.reconciling : undefined)} onRetry={onRetryBatch} />)}
          </ul>}
        </section>
      </>}
    </div>
  </Drawer>;
}
