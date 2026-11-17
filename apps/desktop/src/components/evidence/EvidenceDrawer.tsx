import { useEffect, useId, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { notifyToast } from "../../app/events";
import { formatDateTime } from "../../app/format";
import { useAppStore } from "../../app/store";
import { today } from "../../i18n/zh-CN/today";
import { RpcError, type ActionType, type DecisionDetail } from "../../rpc";
import { Banner, Button, Drawer, Field, Input, Probability, Skeleton, VerdictChip } from "../ui";
import { EvidenceText } from "./EvidenceText";
import { ProbabilityBars } from "./ProbabilityBars";
import "./evidence.css";

export const NOTE_MAX = 200;
export interface EvidenceDrawerProps {
  decisionId: string | null; overlay: boolean; onClose: () => void;
  onAct: (action: ActionType, note: string | null) => Promise<void>; onReopen: () => Promise<void>;
}
export function safeEvidenceUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "www.sec.gov" && !url.port && !url.username && !url.password;
  } catch { return false; }
}
export function EvidenceDrawer(props: EvidenceDrawerProps) {
  return props.decisionId ? <EvidenceSession key={props.decisionId} {...props} decisionId={props.decisionId} /> : null;
}
function EvidenceSession({ decisionId, overlay, onClose, onAct, onReopen }: EvidenceDrawerProps & { decisionId: string }) {
  const client = useAppStore(state => state.client);
  const [detail, setDetail] = useState<DecisionDetail | null>(null), [error, setError] = useState<RpcError | null>(null);
  const [attempt, setAttempt] = useState(0), [note, setNote] = useState(""), [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(false);
  const titleId = useId(), noteId = useId(), locked = useRef(false), active = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  useEffect(() => {
    const controller = new AbortController(); setDetail(null); setError(null);
    if (!client) { setError(new RpcError("INTERNAL", today.decisionLoadFailed)); return; }
    void client.call("decision.get", { decisionId }, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setDetail(result);
    }).catch(error => {
      if (!controller.signal.aborted) setError(error instanceof RpcError ? error : new RpcError("INTERNAL", today.decisionLoadFailed));
    });
    return () => controller.abort();
  }, [client, decisionId, attempt]);
  useEffect(() => {
    if (!detail) return;
    // hash 陈列与 RouterView 的页标题效果同次提交；在其结束后确认抽屉焦点。
    const timer = setTimeout(() => {
      if (document.activeElement === document.body || document.activeElement?.matches("main h1")) document.getElementById(titleId)?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [detail, titleId]);
  const normalized = note.trim(), tooLong = Array.from(normalized).length > NOTE_MAX;
  async function submit(action: ActionType | "reopen") {
    if (locked.current || tooLong || !detail) return;
    locked.current = true; setBusy(true); setActionError(false);
    try { if (action === "reopen") await onReopen(); else await onAct(action, normalized || null); }
    catch { if (active.current) setActionError(true); }
    finally { locked.current = false; if (active.current) setBusy(false); }
  }
  async function openExternal() {
    if (!detail || !safeEvidenceUrl(detail.event.url)) { notifyToast("error", today.linkBlocked); return; }
    try {
      if (isTauri()) await invoke("open_external", { url: detail.event.url });
      else window.open(detail.event.url, "_blank", "noopener,noreferrer");
    } catch { notifyToast("error", today.linkBlocked); }
  }
  const processed = detail?.action && detail.action.action !== "reopen";
  return <Drawer open overlay={overlay} titleId={titleId} onClose={onClose}>
    <div className="c-drawer__head"><div className="u-grow">{detail && <><VerdictChip kind={detail.relation} /><Probability value={detail.headline} /></>}</div>
      <Button variant="icon" icon="x" aria-label={today.close} onClick={onClose} /></div>
    <div className="c-drawer__body">
      <h2 className="c-drawer__title" id={titleId} tabIndex={-1}>{detail ? <><span className="u-mono">{detail.instrument.symbol}</span> · {detail.instrument.name}</> : today.evidence}</h2>
      {!detail && !error && <Skeleton rows={1} />}
      {error && <Banner tone="danger" text={error.code === "NOT_FOUND" ? today.decisionNotFound : today.decisionLoadFailed}
        action={error.code !== "NOT_FOUND" ? <Button onClick={() => setAttempt(n => n + 1)}>{today.retry}</Button> : undefined} />}
      {detail && <>
        <section className="c-drawer__sec"><h3>{today.disclosure}</h3><dl className="c-kv">
          <dt>{today.title}</dt><dd>{detail.event.title}</dd><dt>{today.form}</dt><dd>{detail.event.formType}</dd>
          <dt>{today.published}</dt><dd>{formatDateTime(detail.event.publishedAt)}</dd><dt>{today.file}</dt><dd>{today.fileParts[detail.evidence.filePart as keyof typeof today.fileParts] ?? detail.evidence.filePart}</dd>
        </dl>{/^us:0009990/.test(detail.event.eventId) ? <p className="c-note">{today.demoEvidence}</p> : <>
          {safeEvidenceUrl(detail.event.url) ? <a className="c-link" href={detail.event.url} target="_blank" rel="noopener noreferrer"
            onClick={event => { event.preventDefault(); void openExternal(); }}>{today.external} ↗</a> : <Button variant="text" onClick={() => { void openExternal(); }}>{today.external}</Button>}
          <p className="c-note">{today.externalDomain}</p></>}</section>
        <section className="c-drawer__sec"><h3>{today.passage}</h3><EvidenceText evidence={detail.evidence} titleOnly={detail.contentStatus === "title_only"} /></section>
        <section className="c-drawer__sec"><h3>{today.yourThesis}</h3><blockquote className="c-quote">{detail.thesisStatement}</blockquote>
          <p className="u-small u-text-2">{detail.killCondition ? today.killCondition + detail.killCondition : today.noKillCondition}</p>
          {detail.thesisCurrentVersion > detail.thesisVersion && <p className="c-note">{today.updatedVersion(detail.thesisVersion, detail.thesisCurrentVersion)}</p>}</section>
        <section className="c-drawer__sec"><h3>{today.probability}</h3><ProbabilityBars probabilities={detail.probabilities} /></section>
        <p className="c-note">{today.engines[detail.engine]} · {detail.modelId} · {today.questionSet} {detail.questionSetVersion}</p>
      </>}
    </div>
    {detail && <div className="c-drawer__foot">{actionError && <Banner tone="danger" text={today.actionFailed} />}
      {processed ? <><p>{today.processedLabel}<strong>{today.actions[detail.action!.action]}</strong>{detail.action!.note ? ` · ${detail.action!.note}` : ""} · {formatDateTime(detail.action!.actedAt)}</p>
        <Button disabled={busy} onClick={() => { void submit("reopen"); }}>{today.actions.reopen}</Button></> : <>
        <Field id={noteId} label={today.note} error={tooLong ? today.noteTooLong : undefined} count={{ value: Array.from(normalized).length, max: NOTE_MAX }}>
          <Input value={note} onChange={event => setNote(event.target.value)} placeholder={today.notePlaceholder} disabled={busy} /></Field>
        <div className="c-drawer__actions">{(["still_valid", "revise", "exit_intent", "ignore"] as const).map(action => <Button key={action}
          variant={action === "still_valid" ? "primary" : action === "ignore" ? "text" : "secondary"} disabled={busy || tooLong}
          onClick={() => { void submit(action); }}>{today.actions[action]}</Button>)}</div>
      </>}
    </div>}
  </Drawer>;
}
