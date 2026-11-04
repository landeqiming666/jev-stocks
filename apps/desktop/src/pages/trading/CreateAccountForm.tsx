import { useState, type FormEvent } from "react";
import { Banner, Button, Field, Input } from "../../components/ui";
import { trading as t } from "../../i18n/zh-CN/trading";
import { RpcError, type ParamsOf } from "../../rpc";
import { validateAccount } from "./validation";

export const DEFAULT_CASH = "100000.00";
export function CreateAccountForm({ defaultDate, busy, onCreate, onCancel }: {
  defaultDate: string; busy: boolean; onCreate: (input: ParamsOf<"paper.createAccount">) => Promise<unknown>; onCancel?: () => void;
}) {
  const [input, setInput] = useState({ name: "", initialCash: DEFAULT_CASH, startDate: defaultDate });
  const [errors, setErrors] = useState<ReturnType<typeof validateAccount>>({});
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    const errors = validateAccount(input); setErrors(errors); setError(null);
    if (Object.keys(errors).length) return;
    try { await onCreate({ ...input, name: input.name.trim() }); }
    catch (error) {
      if (error instanceof RpcError && ["name", "initialCash", "startDate"].includes(String(error.data.field)))
        setErrors({ [String(error.data.field)]: error.message });
      else setError(error instanceof RpcError ? error.message : t.failed);
    }
  }
  return <form className="c-card p-trading__create" onSubmit={submit} noValidate>
    <h2 className="c-card__title">{t.createTitle}</h2><p className="u-text-2">{t.createHelp}</p>
    {error && <Banner tone="danger" text={error} />}
    <div className="p-stack"><Field id="acc-name" label={t.name} error={errors.name} count={{ value: 0, max: 30 }}>
      <Input value={input.name} onChange={event => setInput({ ...input, name: event.target.value })} disabled={busy} autoComplete="off" />
    </Field><Field id="acc-cash" label={t.initialCash} error={errors.initialCash}>
      <Input inputMode="decimal" value={input.initialCash} onChange={event => setInput({ ...input, initialCash: event.target.value })} disabled={busy} />
    </Field><Field id="acc-start" label={t.startDate} help={t.startHelp} error={errors.startDate}>
      <Input type="date" value={input.startDate} onChange={event => setInput({ ...input, startDate: event.target.value })} disabled={busy} />
    </Field><div className="p-trading__actions"><Button type="submit" variant="primary" loading={busy}>{t.create}</Button>
      {onCancel && <Button disabled={busy} onClick={onCancel}>{t.cancel}</Button>}</div></div>
  </form>;
}
