import { useRef, useState, type KeyboardEvent } from "react";
import { useAppStore } from "../../app/store";
import { Banner, Button, Input, Textarea } from "../../components/ui";
import { Field } from "./PortfolioField";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import { RpcError } from "../../rpc";
import type { Thesis } from "../../rpc/generated/types";
import { Confirm } from "./Confirm";
import { errorText } from "./use-resource";
import { useDraft, type DraftState } from "./use-draft";
import { countText, KILL_MAX, STATEMENT_MAX, trimText, validateThesis } from "./validation";

export function ThesisEditor({ instrumentId, initial, template = "", onSaved, onCancel, onState }: {
  instrumentId: string; initial?: Thesis | null; template?: string; onSaved: (t: Thesis) => void;
  onCancel: () => void; onState?: DraftState;
}) {
  const client = useAppStore(s => s.client);
  const [statement, setStatement] = useState(initial?.statement ?? template);
  const [kill, setKill] = useState(initial?.killCondition ?? "");
  const [expectedVersion, setExpectedVersion] = useState(initial?.version ?? 1);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState<Thesis | null>(null);
  const [cancelConfirm, setCancelConfirm] = useState(false);
  const dirty = statement !== (initial?.statement ?? "") || kill !== (initial?.killCondition ?? "");
  const focus = useDraft(dirty, busy, onState);
  const result = validateThesis(statement, kill);
  const statementError = countText(statement) > STATEMENT_MAX ? text.thesisTooLong : submitted && !trimText(statement) ? text.thesisEmpty : undefined;
  const killError = countText(kill) > KILL_MAX ? text.killTooLong : undefined;
  const cancel = () => { if (!lock.current) { if (dirty) setCancelConfirm(true); else onCancel(); } };
  async function save() {
    if (lock.current || conflict) return;
    setSubmitted(true); setError(null);
    if (!result.ok) return;
    if (!client) { setError(text.disconnected); return; }
    lock.current = true; setBusy(true);
    try {
      const input = { statement: result.statement, killCondition: result.killCondition };
      const saved = initial ? await client.call("thesis.update", { ...input, thesisId: initial.thesisId, expectedVersion }) :
        await client.call("thesis.create", { ...input, instrumentId });
      onSaved(saved);
    } catch (error) {
      if (error instanceof RpcError && error.code === "CONFLICT") { setConflict(true); setLatest(null); }
      else if (error instanceof RpcError && error.code === "INVALID_ARGUMENT" && error.data.field === "instrumentId" && error.data.max === 5) setError(text.thesisLimit);
      else setError(errorText(error, text.saveFailed));
    } finally { lock.current = false; setBusy(false); }
  }
  async function refreshLatest() {
    if (!client || !initial || lock.current) return;
    lock.current = true; setBusy(true); setError(null);
    try {
      const { items } = await client.call("thesis.list", { instrumentId });
      const current = items.find(t => t.thesisId === initial.thesisId && t.status === "active");
      setLatest(current ?? null);
      if (!current) setError(text.latestMissing);
    } catch (error) { setError(errorText(error)); }
    finally { lock.current = false; setBusy(false); }
  }
  function keydown(event: KeyboardEvent) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); cancel(); }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); void save(); }
  }
  return <section className="p-holdings__editor" aria-label={text.editor} aria-busy={busy} onKeyDown={keydown}>
    {conflict && <Banner tone="warn" text={text.thesisConflict} action={<Button loading={busy} onClick={() => void refreshLatest()}>{text.refresh}</Button>} />}
    {latest && <div className="p-holdings__latest"><h3>{text.latest} · {text.version(latest.version, latest.versionCount)}</h3>
      <p>{latest.statement}</p>{latest.killCondition && <p>{text.killPrefix}{latest.killCondition}</p>}
      <Button disabled={busy} onClick={() => { setExpectedVersion(latest.version); setConflict(false); setLatest(null); }}>{text.useLatest(latest.version)}</Button>
    </div>}
    {error && <Banner tone="danger" text={error} />}
    <Field id="holding-statement" label={text.statement} help={text.editorHelp} error={statementError} count={{ value: countText(statement), max: STATEMENT_MAX }}>
      <Textarea ref={node => { focus.current = node; }} value={statement} disabled={busy}
        placeholder={text.statementPlaceholder} onChange={e => setStatement(e.target.value)} />
    </Field>
    <Field id="holding-kill" label={text.kill} error={killError} count={{ value: countText(kill), max: KILL_MAX }}>
      <Input value={kill} disabled={busy} placeholder={text.killPlaceholder} onChange={e => setKill(e.target.value)} />
    </Field>
    <div className="p-holdings__actions"><Button variant="primary" loading={busy} disabled={conflict} onClick={() => void save()}>{text.save}</Button>
      <Button variant="text" disabled={busy} onClick={cancel}>{text.cancel}</Button></div>
    {cancelConfirm && <Confirm title={text.unsaved} description={text.unsavedHelp} accept={text.discard} cancel={text.keepEditing}
      onAccept={onCancel} onCancel={() => setCancelConfirm(false)} />}
  </section>;
}
