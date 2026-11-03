import { useId } from "react";
import { Button, Modal } from "../../components/ui";
import { holdings as text } from "../../i18n/zh-CN/holdings";

export function Confirm({ title, description, accept, cancel = text.cancel, busy = false, error, onAccept, onCancel }: {
  title: string; description: string; accept: string; cancel?: string; busy?: boolean; error?: string | null;
  onAccept: () => void; onCancel: () => void;
}) {
  const id = useId();
  return <Modal open titleId={id} onClose={() => { if (!busy) onCancel(); }}>
    <h2 id={id}>{title}</h2><p>{description}</p>
    {error && <p role="alert" className="u-danger">{error}</p>}
    <div className="p-holdings__actions">
      <Button variant="danger" loading={busy} onClick={onAccept}>{accept}</Button>
      <Button disabled={busy} onClick={onCancel}>{cancel}</Button>
    </div>
  </Modal>;
}
