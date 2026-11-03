import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { navigate } from "../../app/events";
import { formatDateTime } from "../../app/format";
import { useAppStore } from "../../app/store";
import { today } from "../../i18n/zh-CN/today";
import { useRoute } from "../../router/useRoute";
import type { ActionType, Bootstrap, MockRpcClient, RpcClient } from "../../rpc";
import { MOCK_EXAMPLES } from "../../rpc/generated/mock-data";
import { SCENARIOS } from "../../mocks/scenarios";
import { PageFrame } from "../../shell/PageFrame";
import { Banner, Button, Card, EmptyState, Progress, Skeleton } from "../../components/ui";
import { EvidenceDrawer } from "../../components/evidence/EvidenceDrawer";
import { DecisionGroups } from "./DecisionGroups";
import { TodayHeader } from "./TodayHeader";
import { deriveTodayState, sortDecisions } from "./state";
import { useInbox } from "./useInbox";
import { useScanControl } from "./useScanControl";
import "./today.css";

export const DRAWER_PUSH_BP = 1200;
export { useInbox, useScanControl };
export function TodayPage() {
  const client = useAppStore(state => state.client), boot = useAppStore(state => state.bootstrap.value);
  const { params } = useRoute();
  if (!client || !boot) return <PageFrame><Skeleton rows={3} /></PageFrame>;
  if (import.meta.env.VITE_RPC === "mock" && "setExample" in client) return <MockToday key={params.toString()} client={client as MockRpcClient} query={params.toString()} />;
  return <TodayContent client={client} boot={boot} />;
}
export default TodayPage;

function MockToday({ client, query }: { client: MockRpcClient; query: string }) {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const params = new URLSearchParams(query), state = params.get("state") ?? "pending", drawer = params.get("drawer");
  const selected = MOCK_EXAMPLES["decision.get"].find(example => example.name === drawer);
  useEffect(() => {
    const controller = new AbortController(), params = new URLSearchParams(query);
    const state = params.get("state") ?? "pending", drawer = params.get("drawer");
    const scenario = SCENARIOS[`today.${state}`] ?? SCENARIOS["today.pending"]!;
    useAppStore.getState().setScanProgress(null);
    client.setExample("app.bootstrap", scenario.examples["app.bootstrap"] ?? "ready");
    client.setExample("inbox.list", scenario.examples["inbox.list"] ?? "pending");
    const detail = MOCK_EXAMPLES["decision.get"].find(example => example.name === drawer);
    client.setExample("decision.get", detail?.name ?? "overturn");
    void client.call("app.bootstrap", {}, { signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      useAppStore.setState({ bootstrap: { status: "ready", value, error: null } }); setBoot(value);
    }).catch(() => {});
    return () => controller.abort();
  }, [client, query]);
  return boot ? <TodayContent client={client} boot={boot} previewState={state} previewDecision={selected?.params.decisionId} /> : <PageFrame><Skeleton rows={3} /></PageFrame>;
}
function TodayContent({ client, boot, previewState, previewDecision }: {
  client: RpcClient; boot: Bootstrap; previewState?: string; previewDecision?: string;
}) {
  const inbox = useInbox(client);
  const scan = useScanControl(client, ["running", "queued"].includes(inbox.inbox?.lastScan?.status ?? "") ? inbox.inbox!.lastScan!.runId : null);
  const [selected, setSelected] = useState<string | null>(previewDecision ?? null);
  const [overlay, setOverlay] = useState(() => window.innerWidth < DRAWER_PUSH_BP);
  const [focus, setFocus] = useState<{ id: string; action?: string } | null>(null);
  const active = useRef(true), opener = useRef<string | null>(null), pageFocused = useRef(false);
  useEffect(() => {
    active.current = true;
    const media = window.matchMedia(`(max-width: ${DRAWER_PUSH_BP - 1}px)`);
    const change = () => setOverlay(media.matches);
    media.addEventListener("change", change);
    return () => { active.current = false; media.removeEventListener("change", change); };
  }, []);
  useEffect(() => {
    useAppStore.getState().setDrawerOpen(selected !== null);
    return () => useAppStore.getState().setDrawerOpen(false);
  }, [selected]);
  useEffect(() => {
    if (previewState === "scanning" && import.meta.env.VITE_RPC === "mock" && "injectNotification" in client) (client as MockRpcClient).injectNotification("scan.progress");
  }, [client, previewState]);
  useEffect(() => {
    if (inbox.inbox?.lastScan?.status !== "failed") return;
    const controller = new AbortController();
    void client.call("scan.history", { limit: 30 }, { signal: controller.signal }).then(history => {
      if (controller.signal.aborted || useAppStore.getState().client !== client) return;
      const at = history.items.filter(run => run.status === "succeeded" && run.finishedAt).map(run => run.finishedAt!).sort().at(-1);
      if (at && at > (useAppStore.getState().lastSuccessfulScanAt ?? "")) useAppStore.getState().setLastSuccessfulScanAt(at);
    }).catch(() => {});
    return () => controller.abort();
  }, [client, inbox.inbox?.lastScan?.runId, inbox.inbox?.lastScan?.status]);
  useLayoutEffect(() => {
    if (!focus) return;
    const heading = document.getElementById(`t-${focus.id}`);
    const target = focus.action ? heading?.closest("article")?.querySelector<HTMLElement>(`[data-action="${focus.action}"]`) : heading;
    const visible = target && !target.closest("details:not([open])");
    (visible ? target : document.querySelector<HTMLElement>(".p-today h1"))?.focus({ preventScroll: true });
  }, [focus]);
  const close = useCallback(() => {
    setSelected(null);
    if (opener.current) setFocus({ id: opener.current, action: "open" });
  }, []);
  const open = (id: string) => {
    opener.current = id;
    if (import.meta.env.VITE_RPC === "mock" && "setExample" in client) {
      const example = MOCK_EXAMPLES["decision.get"].find(example => example.params.decisionId === id);
      if (example) (client as MockRpcClient).setExample("decision.get", example.name);
    }
    setSelected(id);
  };
  const actOn = async (id: string, action: ActionType, note?: string) => {
    if (action === "revise") {
      const item = [...(inbox.inbox?.items ?? []), ...(inbox.inbox?.uncertain ?? [])].find(item => item.decisionId === id);
      close(); if (item) navigate("holdings", { thesis: item.thesisId }); return;
    }
    const origin = document.activeElement as HTMLElement;
    const group = inbox.inbox?.uncertain.some(item => item.decisionId === id) ? inbox.inbox.uncertain : inbox.inbox?.items ?? [];
    const sorted = sortDecisions(group), index = sorted.findIndex(item => item.decisionId === id);
    const next = sorted[index + 1] ?? sorted[index - 1];
    try {
      await inbox.act(id, action, note);
      if (active.current) { close(); setFocus({ id: next?.decisionId ?? "" }); }
    } catch (error) {
      if (active.current) {
        if (selected) { if (origin.isConnected) origin.focus(); }
        else setFocus({ id, action: origin.dataset.action ?? "more" });
      }
      throw error;
    }
  };
  const reopen = async (id: string) => {
    try { await inbox.reopen(id); if (active.current) { close(); setFocus({ id }); } }
    catch (error) { if (active.current && !selected) document.querySelector<HTMLElement>(`[data-decision-id="${id}"]`)?.focus(); throw error; }
  };
  const data = inbox.inbox, loading = !data && inbox.state === "loading" || previewState === "loading";
  const state = deriveTodayState(data, boot), pending = data?.items.length ?? 0;
  const empty = !!data && !pending && !data.uncertain.length && !!data.lastScan;
  const title = loading ? today.loading : !data ? today.page : pending ? today.pending(pending) : data.uncertain.length ? today.uncertainOnly : empty ? undefined : today.page;
  useLayoutEffect(() => {
    if (!loading && inbox.state !== "loading" && !selected && !pageFocused.current) {
      const heading = document.querySelector<HTMLElement>(".p-today h1");
      if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); pageFocused.current = true; }
    }
  }, [loading, inbox.state, selected]);
  const drawer = <EvidenceDrawer decisionId={selected} overlay={overlay} onClose={close}
    onAct={(action, note) => actOn(selected!, action, note ?? undefined)} onReopen={() => reopen(selected!)} />;
  return <div className="p-today-frame">
    {!loading && data?.lastScan?.status === "failed" && <div className="l-banners p-today-alerts"><Banner tone="danger" text={data.lastScan.error?.message ?? today.scanFailedHelp}
      action={<Button disabled={!!scan.runId || scan.conflict || !boot.configured.jevKey || !boot.configured.secEmail || boot.offline || data.dataStatus.offline} onClick={() => { void scan.start(); }}>{today.retry}</Button>} /></div>}
    <PageFrame asideOpen={!!selected && !overlay} aside={drawer} asideLabel={today.evidence}>
    <section className="p-today" data-ready={!loading && inbox.state !== "loading"} data-state={loading ? "loading" : state}>
      <TodayHeader boot={boot} inbox={data} title={title} start={scan.start} cancel={scan.cancel}
        running={!!scan.runId} starting={scan.starting} cancelling={scan.cancelling} conflict={scan.conflict} loading={loading} />
      {loading ? <Skeleton rows={3} /> : <>
        {inbox.error && <Banner tone="danger" text={today.loadFailed} action={<Button onClick={() => { void inbox.refresh(); }}>{today.retry}</Button>} />}
        {state === "unconfigured" && <Banner tone="info" text={today.configRequired} action={<Button onClick={() => navigate("settings")}>{today.goSettings}</Button>} />}
        {(boot.offline || data?.dataStatus.offline) && <p className="c-note">{today.cachedResults}</p>}
        {previewState === "engine_fallback" && <Banner tone="info" text={today.engineFallback} />}
        {scan.progress && <div className="p-today__scan"><Card><strong>{today.scanning}</strong><p className="c-note">{scan.progress.message}</p><Progress value={scan.progress.done} max={scan.progress.total} label={today.progress} /></Card></div>}
        {data && <>
          {state === "no_holdings" ? <EmptyState title={today.noHoldings} text={today.noHoldingsHelp} action={<Button variant="primary" onClick={() => navigate("holdings")}>{today.goHoldings}</Button>} /> :
            !pending && !data.uncertain.length && !data.lastScan ? <EmptyState title={today.neverScanned} text={today.neverScannedHelp(data.setup.scannableInstruments)} /> :
            empty ? <EmptyState display title={today.empty} text={today.checked(data.lastScan!.stats.instruments, data.lastScan!.stats.filings, data.lastScan!.stats.passages, data.lastScan!.finishedAt ? formatDateTime(data.lastScan!.finishedAt) : "—")} /> : null}
          <DecisionGroups inbox={data} onOpen={open} onAct={(id, action, note) => { void actOn(id, action, note).catch(() => {}); }} onReopen={id => { void reopen(id).catch(() => {}); }} />
          {!!data.lastScan?.stats.skippedNoThesis && <p className="c-note">{today.skipped(data.lastScan.stats.skippedNoThesis)}</p>}
          <div className="p-today__refresh"><Button variant="text" icon="refresh-cw" onClick={() => { void inbox.refresh(); }}>{today.refresh}</Button></div>
        </>}
      </>}
    </section>
  </PageFrame>{overlay && drawer}</div>;
}
