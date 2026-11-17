import { useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import { PageFrame } from "../../shell/PageFrame";
import { useOnline } from "../../lib/online";
import { useRoute } from "../../router/useRoute";
import { Banner } from "../../components/ui/Banner";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { scan } from "../../i18n/zh-CN/scan";
import { BudgetBar } from "./BudgetBar";
import { ScanHeader } from "./ScanHeader";
import { RunTable } from "./RunTable";
import { RunDetailDrawer } from "./RunDetailDrawer";
import { useScanRuns, type ScanControl } from "./useScanRuns";
import { selectMockScenario } from "./mock-scenario";
import "./scan.css";

function useOverlay() {
  const [overlay, setOverlay] = useState(() => window.innerWidth < 1200);
  useEffect(() => {
    const resize = () => setOverlay(window.innerWidth < 1200);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return overlay;
}
export default function ScanPage({ control: suppliedControl }: { control?: ScanControl } = {}) {
  const client = useAppStore(state => state.client);
  const bootstrap = useAppStore(state => state.bootstrap.value);
  const dataOffline = useAppStore(state => state.dataStatus?.offline);
  const online = useOnline();
  const { params } = useRoute();
  const mockState = import.meta.env.VITE_RPC === "mock" ? params.get("state") ?? "default" : "";
  useEffect(() => { selectMockScenario(client, mockState); }, [client, mockState]);
  const data = useScanRuns(client, mockState);
  const { loading, runs, open } = data;
  const openedMock = useRef<string | null>(null);
  useEffect(() => {
    if (mockState !== "detail") { openedMock.current = null; return; }
    if (!loading && openedMock.current !== mockState && runs.length) {
      openedMock.current = mockState;
      const run = runs.find(run => run.status === "partial");
      if (run) open(run.runId);
    }
  }, [mockState, loading, runs, open]);
  const control = suppliedControl ?? data.control;
  const overlay = useOverlay();
  const configured = bootstrap?.configured.jevKey && bootstrap.configured.secEmail;
  const exhausted = data.budget !== null && data.budget.limitTokens > 0 && data.budget.usedTokens >= data.budget.limitTokens;
  const disabledReason = !configured ? scan.configRequired : !online || bootstrap?.offline || dataOffline ? scan.offline : exhausted ? scan.budgetExhausted : undefined;
  const startReason = disabledReason ?? (data.loading || !data.budget || !client || client.status() !== "ready" ? scan.loading : undefined);
  const drawer = <RunDetailDrawer runId={data.selected} overlay={overlay} detail={data.detail} loading={data.detailLoading}
    error={data.detailError} retryErrors={data.retryErrors} retrying={data.retrying} reconciling={data.reconciling} disabledReason={disabledReason || (control.activeRunId ? scan.runningConflict : undefined)}
    onClose={data.close} onRetryBatch={data.retry} onRefresh={data.refreshDetail} />;
  return <>
    <PageFrame aside={overlay ? undefined : drawer} asideOpen={!overlay && Boolean(data.selected)} asideLabel={scan.details}>
      <section className="p-scan" data-ready={!data.loading && !data.detailLoading}>
        <ScanHeader control={control} disabledReason={startReason} lastRun={data.runs[0]} />
        {data.actionError && <Banner tone="danger" text={`${data.actionError.code} · ${data.actionError.message}`} />}
        {data.error && <Banner tone="danger" text={`${scan.loadFailed} ${data.error.code} · ${data.error.message}`}
          action={<Button onClick={() => { void data.refresh(); }}>{scan.retry}</Button>} />}
        {data.budget && <BudgetBar {...data.budget} />}
        {data.loading && !data.runs.length ? <div aria-label={scan.loading} role="status" className="p-scan__skeleton">
          <Skeleton rows={4} />
        </div> : data.runs.length ? <RunTable items={data.runs} selected={data.selected} progress={data.progress} onOpen={data.open} /> :
          !data.error && <EmptyState title={scan.empty} text={scan.emptyHelp} />}
        {data.nextCursor && <div className="p-scan__pagination"><Button loading={data.loadingMore} disabled={data.loading}
          onClick={() => { void data.loadMore(); }}>{scan.more}</Button></div>}
      </section>
    </PageFrame>
    {overlay && drawer}
  </>;
}
