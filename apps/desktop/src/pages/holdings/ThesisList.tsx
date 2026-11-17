import { useRef, useState, type ReactNode } from "react";
import { useAppStore } from "../../app/store";
import { formatDate } from "../../app/format";
import { notifyToast } from "../../app/events";
import { Banner, Button, Icon } from "../../components/ui";
import type { IconName } from "../../components/ui";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import type { Thesis } from "../../rpc/generated/types";
import { useTheses } from "./useTheses";
import { ThesisEditor } from "./ThesisEditor";
import { VersionHistory } from "./VersionHistory";
import { Confirm } from "./Confirm";
import type { DraftState } from "./use-draft";
import { MAX_THESES } from "./validation";
import { useFocusReturn } from "./use-focus-return";

const verdicts = {
  overturn: ["over", "alert-triangle"], weaken: ["weak", "arrow-down"], support: ["hold", "check"],
  none: ["none", "minus"], uncertain: ["unsure", "help-circle"],
} satisfies Record<string, [string, IconName]>;
export function ThesisList({ instrumentId, onChanged, onState, disabled = false, holdingActions }: {
  instrumentId: string; onChanged: () => void; onState: DraftState; disabled?: boolean; holdingActions?: ReactNode;
}) {
  const client = useAppStore(s => s.client);
  const resource = useTheses(client, instrumentId);
  const [editor, setEditor] = useState<{ initial?: Thesis; template?: string } | null>(null);
  const returnId = useRef("");
  const focusLater = useFocusReturn();
  const [history, setHistory] = useState<string | null>(null);
  const [archive, setArchive] = useState<Thesis | null>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  async function confirmArchive() {
    if (!archive || !client || lock.current) return;
    lock.current = true; setBusy(true); onState(false, true); setError(null);
    try {
      await client.call("thesis.archive", { thesisId: archive.thesisId });
      setArchive(null); await resource.refresh(); onChanged();
    } catch { setError(text.archiveFailed); notifyToast("error", text.archiveFailed); }
    finally { lock.current = false; setBusy(false); onState(false, false); }
  }
  function closeEditor() {
    setEditor(null);
    focusLater(returnId.current);
  }
  function openEditor(value: { initial?: Thesis; template?: string }, id: string) { returnId.current = id; setEditor(value); }
  function saved() { closeEditor(); void resource.refresh(); onChanged(); }
  if (resource.loading && !resource.value) return <p role="status">{text.loading}</p>;
  if (resource.error) return <Banner tone="danger" text={resource.error} action={<Button onClick={() => void resource.refresh()}>{text.retry}</Button>} />;
  return <div className="p-holdings__theses">
    {resource.items.map(t => editor?.initial?.thesisId === t.thesisId ?
      <ThesisEditor key={t.thesisId} instrumentId={instrumentId} initial={editor.initial} onSaved={saved} onCancel={closeEditor} onState={onState} /> :
      <article className="p-holdings__thesis" key={t.thesisId}>
        <p>{t.statement}</p>{t.killCondition && <p className="p-holdings__kill">{text.killPrefix}{t.killCondition}</p>}
        <div className="p-holdings__meta"><span>{text.version(t.version, t.versionCount)}</span><span>{text.created} {formatDate(t.createdAt)}</span>
          {t.lastDecision ? <><span>{text.lastDecision}</span><span className={`c-verdict c-verdict--${verdicts[t.lastDecision.relation][0]}`}>
            <Icon name={verdicts[t.lastDecision.relation][1]} />{text.relation[t.lastDecision.relation]}</span></> : <span>{text.noDecision}</span>}
        </div>
        <div className="p-holdings__thesis-actions"><Button id={`edit-${t.thesisId}`} variant="text" disabled={!!editor || disabled} onClick={() => openEditor({ initial: t }, `edit-${t.thesisId}`)}>{text.edit}</Button>
          <Button variant="text" disabled={!!editor || disabled} onClick={() => setHistory(t.thesisId)}>{text.versions}</Button>
          <Button variant="text" disabled={!!editor || disabled} onClick={() => { setArchive(t); setError(null); }}>{text.archive}</Button></div>
      </article>)}
    {editor && !editor.initial && <ThesisEditor instrumentId={instrumentId} template={editor.template} onSaved={saved} onCancel={closeEditor} onState={onState} />}
    {!resource.items.length && !editor && <div className="c-card"><h2 className="c-card__title">{text.noThesis}</h2><p className="u-text-2">{text.noThesisHelp}</p>
      <div className="p-holdings__actions">{text.templates.map((template, index) => <Button key={template} id={`template-${index}`} disabled={disabled} onClick={() => openEditor({ template }, `template-${index}`)}>{template}</Button>)}</div></div>}
    {!editor && <div className="p-holdings__actions"><Button icon="plus" disabled={disabled || resource.items.length >= MAX_THESES}
      id={`add-thesis-${instrumentId}`} disabledReason={text.thesisLimit} onClick={() => openEditor({}, `add-thesis-${instrumentId}`)}>{text.addThesis}</Button>
      {resource.items.length >= MAX_THESES && <span className="u-muted">{text.thesisLimit}</span>}{holdingActions}</div>}
    {history && <VersionHistory thesisId={history} onClose={() => setHistory(null)} />}
    {archive && <Confirm title={text.archive} description={text.archiveHelp} accept={text.confirmArchive} busy={busy} error={error}
      onAccept={() => void confirmArchive()} onCancel={() => setArchive(null)} />}
  </div>;
}
