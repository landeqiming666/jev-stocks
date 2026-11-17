import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import { notifyToast, REFRESH_EVENT } from "../../app/events";
import { formatDate } from "../../app/format";
import { Banner, Button, EmptyState } from "../../components/ui";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { PageFrame } from "../../shell/PageFrame";
import { useRoute } from "../../router/useRoute";
import type { Holding, Instrument } from "../../rpc/generated/types";
import type { ParamsOf, ResultOf } from "../../rpc";
import { AddInstrument } from "./AddInstrument";
import { HoldingsTable } from "./HoldingsTable";
import { HoldingForm } from "./HoldingForm";
import { ThesisList } from "./ThesisList";
import { Confirm } from "./Confirm";
import { useHoldings } from "./useHoldings";
import { useExitGuard } from "./use-exit-guard";
import { useFocusReturn } from "./use-focus-return";
import "./holdings.css";

export default function HoldingsPage() {
  const client = useAppStore(s => s.client);
  const bootstrap = useAppStore(s => s.bootstrap.value);
  const resource = useHoldings(client);
  const refreshHoldings = resource.refresh;
  const { params } = useRoute(), thesisId = params.get("thesis");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [add, setAdd] = useState<Instrument | null>(null);
  const [edit, setEdit] = useState<Holding | null>(null);
  const [archive, setArchive] = useState<Holding | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [prices, setPrices] = useState<ResultOf<"prices.refresh"> | null>(null);
  const [priceError, setPriceError] = useState<string | null>(null);
  const lock = useRef(false);
  const priceLock = useRef(false);
  const priceRequest = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const guard = useExitGuard(dirty, busy);
  const focusLater = useFocusReturn();
  const onState = useCallback((draft: boolean, saving: boolean) => { setDirty(draft); setBusy(saving); }, []);
  useEffect(() => {
    setRefreshing(false); priceLock.current = false;
    return () => priceRequest.current?.abort();
  }, [client]);
  const dates = resource.items.map(h => h.lastCloseDate).filter((d): d is string => d !== null).sort();
  const date = dates[0] ?? null;
  useEffect(() => {
    if (!client || !thesisId) return;
    const controller = new AbortController();
    void client.call("thesis.list", { status: "active" }, { signal: controller.signal }).then(({ items }) => {
      const thesis = items.find(t => t.thesisId === thesisId);
      if (thesis && thesis.instrumentId.startsWith("us:") && !controller.signal.aborted) setExpanded(thesis.instrumentId);
    }).catch(() => { if (!controller.signal.aborted) notifyToast("error", text.loadFailed); });
    return () => controller.abort();
  }, [client, thesisId]);
  useEffect(() => {
    if (!expanded) return;
    const frame = requestAnimationFrame(() => document.getElementById(`holding-${expanded.slice(3)}`)?.scrollIntoView?.({ block: "nearest" }));
    return () => cancelAnimationFrame(frame);
  }, [expanded, resource.value]);
  useEffect(() => {
    const refresh = () => { void refreshHoldings(); };
    window.addEventListener(REFRESH_EVENT, refresh);
    const off = client?.subscribe("inbox.updated", refresh);
    return () => { window.removeEventListener(REFRESH_EVENT, refresh); off?.(); };
  }, [client, refreshHoldings]);
  function toggle(id: string) { guard.request(() => { setAdd(null); setEdit(null); setExpanded(current => current === id ? null : id); }); }
  async function saveHolding(params: ParamsOf<"holdings.upsert">) {
    await resource.upsert(params); setAdd(null); setEdit(null); setExpanded(params.instrumentId);
  }
  async function confirmArchive() {
    if (!archive || lock.current) return;
    lock.current = true; setBusy(true); setArchiveError(null);
    try { await resource.archive(archive.instrument.instrumentId); setArchive(null); setExpanded(null); }
    catch { setArchiveError(text.archiveFailed); notifyToast("error", text.archiveFailed); }
    finally { lock.current = false; setBusy(false); }
  }
  async function refreshPrices() {
    if (!client || priceLock.current) return;
    const controller = new AbortController(); priceRequest.current = controller;
    priceLock.current = true; setRefreshing(true); setPriceError(null); setPrices(null);
    try {
      const result = await client.call("prices.refresh", { instrumentIds: resource.items.map(h => h.instrument.instrumentId) }, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setPrices(result);
      if (result.updated === 0 && result.failed.length > 0) notifyToast("error", date ? text.offline(formatDate(date)) : text.offlineNoCache);
      await resource.refresh();
    } catch {
      if (controller.signal.aborted) return;
      const message = date ? text.offline(formatDate(date)) : text.offlineNoCache;
      setPriceError(message); notifyToast("error", message);
    } finally { if (priceRequest.current === controller) priceLock.current = false; if (!controller.signal.aborted) setRefreshing(false); }
  }
  return <PageFrame><section className="p-holdings" data-market="us" data-demo={bootstrap?.demoDataLoaded || undefined}>
    <header className="p-holdings__head"><h1 className="p-holdings__title">{text.title}</h1></header>
    <div className="p-holdings__toolbar"><div className="u-grow">
      <AddInstrument existing={resource.items.map(h => h.instrument.instrumentId)} disabled={dirty || busy || !!add || !!edit} inputRef={input}
        onSelect={instrument => { setExpanded(null); setEdit(null); setAdd(instrument); }} />
      <Button icon="refresh-cw" loading={refreshing} disabled={!client || resource.loading || busy || !resource.items.length} onClick={() => void refreshPrices()}>{text.refreshPrices}</Button>
    </div><span className="p-holdings__sub">{date ? `${text.asOf} ${formatDate(date)}` : text.noPrice}</span></div>
    {add && <HoldingForm instrument={add} onSave={saveHolding} onCancel={() => setAdd(null)} onState={onState} />}
    {priceError && <Banner tone="danger" text={priceError} />}
    {prices && <div className="p-holdings__price-status" role="status"><p>{text.updated(prices.updated)} · {formatDate(prices.asOf)}</p>
      {prices.failed.map(failure => { const holding = resource.items.find(h => h.instrument.instrumentId === failure.instrumentId);
        return <p key={failure.instrumentId} className="u-danger">{text.priceError(holding?.instrument.symbol ?? failure.instrumentId, holding?.lastCloseDate ? formatDate(holding.lastCloseDate) : "")} · {text.errors[failure.error.code as keyof typeof text.errors] ?? text.priceFailed}</p>;
      })}</div>}
    {resource.error && <Banner tone="danger" text={resource.error} action={<Button onClick={() => void resource.refresh()}>{text.retry}</Button>} />}
    {resource.loading && !resource.value ? <div role="status" aria-label={text.loading}>{Array.from({ length: 6 }, (_, n) => <div key={n} data-testid="holding-skeleton" className="p-holdings__skeleton" />)}</div> :
      resource.value && !resource.items.length ? <EmptyState title={text.empty} text={text.emptyHelp} action={<Button onClick={() => input.current?.focus()}>{text.goAdd}</Button>} /> :
      resource.value && <HoldingsTable items={resource.items} expandedId={expanded} onToggle={toggle} detail={h => <>
        {edit ? <HoldingForm instrument={h.instrument} initial={edit} onSave={saveHolding} onCancel={() => {
          setEdit(null); focusLater(`edit-holding-${h.instrument.symbol}`);
        }} onState={onState} /> :
          <ThesisList key={h.instrument.instrumentId} instrumentId={h.instrument.instrumentId} onChanged={() => void resource.refresh()} onState={onState}
            holdingActions={<><Button id={`edit-holding-${h.instrument.symbol}`} variant="text" disabled={dirty || busy} onClick={() => setEdit(h)}>{text.editHolding}</Button>
              <Button variant="text" disabled={dirty || busy} onClick={() => { setArchive(h); setArchiveError(null); }}>{text.archiveHolding}</Button>
              {h.note && <span className="p-holdings__note u-muted">{h.note}</span>}</>} />}
      </>} />}
    {archive && <Confirm title={text.archiveHolding} description={text.archiveHelp} accept={text.confirmArchive} error={archiveError} busy={busy}
      onAccept={() => void confirmArchive()} onCancel={() => setArchive(null)} />}
    {guard.pending && <Confirm title={text.unsaved} description={text.unsavedHelp} accept={text.discard} cancel={text.keepEditing}
      onAccept={guard.discard} onCancel={guard.cancel} />}
  </section></PageFrame>;
}
