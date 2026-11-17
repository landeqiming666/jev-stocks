import { useRef, useState, type KeyboardEvent } from "react";
import { Banner, Button, Input } from "../../components/ui";
import { Field } from "./PortfolioField";
import { holdings as text } from "../../i18n/zh-CN/holdings";
import type { Holding, Instrument } from "../../rpc/generated/types";
import type { ParamsOf } from "../../rpc";
import { Confirm } from "./Confirm";
import { useDraft, type DraftState } from "./use-draft";
import { countText, NOTE_MAX, validateHolding } from "./validation";
import { errorText } from "./use-resource";

export function HoldingForm({ instrument, initial, onSave, onCancel, onState }: {
  instrument: Instrument; initial?: Holding; onSave: (input: ParamsOf<"holdings.upsert">) => Promise<unknown>;
  onCancel: () => void; onState: DraftState;
}) {
  const [quantity, setQuantity] = useState(initial?.quantity ?? "0");
  const [cost, setCost] = useState(initial?.avgCost ?? "");
  const [note, setNote] = useState(initial?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const lock = useRef(false);
  const dirty = quantity !== (initial?.quantity ?? "0") || cost !== (initial?.avgCost ?? "") || note !== (initial?.note ?? "");
  const focus = useDraft(dirty, busy, onState);
  const result = validateHolding(quantity, cost, note);
  const fieldError = (field: "quantity" | "avgCost" | "note") => submitted && !result.ok && result.field === field ? result.message : undefined;
  const cancel = () => { if (!lock.current) { if (dirty) setConfirm(true); else onCancel(); } };
  async function save() {
    if (lock.current) return;
    setSubmitted(true); setError(null);
    if (!result.ok) return;
    lock.current = true; setBusy(true);
    try {
      await onSave({ instrumentId: instrument.instrumentId, quantity: result.quantity, avgCost: result.avgCost, note: result.note });
    } catch (error) { setError(errorText(error, text.saveFailed)); }
    finally { lock.current = false; setBusy(false); }
  }
  function keydown(event: KeyboardEvent) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); cancel(); }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); void save(); }
  }
  return <section className="p-holdings__editor" aria-label={text.editHolding} aria-busy={busy} onKeyDown={keydown}>
    <h2 className="u-h2">{instrument.symbol} · {initial ? text.editHolding : text.add}</h2>
    {error && <Banner tone="danger" text={error} />}
    <div className="p-holdings__form">
      <Field id="holding-quantity" label={text.quantity} help={text.watchHelp} error={fieldError("quantity")}>
        <Input ref={node => { focus.current = node; }} value={quantity} inputMode="decimal" numeric disabled={busy} onChange={e => setQuantity(e.target.value)} />
      </Field>
      <Field id="holding-cost" label={text.cost} help={text.decimalRange} error={fieldError("avgCost")}>
        <Input value={cost} inputMode="decimal" numeric disabled={busy} onChange={e => setCost(e.target.value)} />
      </Field>
      <Field id="holding-note" label={text.note} error={countText(note) > NOTE_MAX ? text.noteLong : fieldError("note")} count={{ value: countText(note), max: NOTE_MAX }}>
        <Input value={note} disabled={busy} onChange={e => setNote(e.target.value)} />
      </Field>
    </div>
    <div className="p-holdings__actions"><Button variant="primary" loading={busy} onClick={() => void save()}>{text.saveHolding}</Button>
      <Button variant="text" disabled={busy} onClick={cancel}>{text.cancel}</Button></div>
    {confirm && <Confirm title={text.unsaved} description={text.unsavedHelp} accept={text.discard} cancel={text.keepEditing}
      onAccept={onCancel} onCancel={() => setConfirm(false)} />}
  </section>;
}
