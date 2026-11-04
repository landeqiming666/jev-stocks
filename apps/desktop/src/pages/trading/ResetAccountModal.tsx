import { useRef, useState, type FormEvent } from "react";
import { Banner, Button, Field, Input, Modal } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import type { PaperAccount } from "../../rpc";

export function ResetAccountModal({ account, open, busy, onReset, onClose }: {
  account: PaperAccount; open: boolean; busy: boolean; onReset: (confirmText: string) => Promise<unknown>; onClose: () => void;
}) {
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (confirmText !== account.name || busy || submitting.current) return;
    submitting.current = true; setError(null);
    try { await onReset(confirmText); onClose(); }
    catch (error) { setError(error instanceof Error ? error.message : t.failed); }
    finally { submitting.current = false; }
  }
  return <Modal open={open} titleId="reset-title" onClose={() => { if (!busy && !submitting.current) onClose(); }}>
    <form onSubmit={submit}><h2 id="reset-title" className="u-h2">{t.resetTitle}</h2>
      <p className="c-note">{t.resetHelp}</p>{error && <Banner tone="danger" text={error} />}
      <Field id="reset-confirm" label={t.resetInput} help={t.confirmAccount(account.name)}>
        <Input value={confirmText} disabled={busy} autoComplete="off" onChange={event => setConfirmText(event.target.value)} />
      </Field><div className="c-modal__actions"><Button disabled={busy} onClick={onClose}>{t.cancel}</Button>
        <Button variant="danger" type="submit" loading={busy} disabled={confirmText !== account.name} disabledReason={t.confirmMismatch}>{t.resetConfirm}</Button>
      </div></form>
  </Modal>;
}
