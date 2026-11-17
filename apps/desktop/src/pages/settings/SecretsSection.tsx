import { useEffect, useRef, useState } from "react";
import { Banner, Button, Field, Input, Modal, StatusTag } from "../../components/ui";
import { settings as text } from "../../i18n/zh-CN/settings";
import { KEY_MAX, normalize, validateEmail, validateKey } from "./validation";
import type { SettingsController } from "./useSettings";
import { useDraft } from "./useDraft";
import { Section } from "./Section";

export function SecretsSection({ state }: { state: SettingsController }) {
  const input = useRef<HTMLInputElement>(null), [replacing, setReplacing] = useState(false);
  const replaceButton = useRef<HTMLButtonElement>(null), pendingFocus = useRef<"replace" | "input" | null>(null);
  const [keyError, setKeyError] = useState<string>(), [emailError, setEmailError] = useState<string>();
  const [confirming, setConfirming] = useState(false), email = useDraft(state.settings!.secContactEmail ?? "");
  const saved = state.secretStatus!.jevKey;
  useEffect(() => { if (replacing) input.current?.focus(); }, [replacing]);
  useEffect(() => {
    if (state.busy || confirming || !pendingFocus.current) return;
    const target = pendingFocus.current === "replace" ? replaceButton.current : input.current;
    if (target) { pendingFocus.current = null; target.focus(); }
  }, [state.busy, saved, replacing, confirming]);
  async function saveKey() {
    const value = input.current?.value ?? "";
    if (!validateKey(value)) { setKeyError(text.invalidKey); input.current?.focus(); return; }
    setKeyError(undefined);
    await state.saveKey(normalize(value), () => {
      if (input.current) input.current.value = "";
      pendingFocus.current = "replace";
      setReplacing(false);
    });
  }
  async function saveEmail() {
    const submitted = email.value;
    if (!validateEmail(submitted)) { setEmailError(text.invalidEmail); return; }
    setEmailError(undefined);
    const value = normalize(submitted);
    if (await state.update({ secContactEmail: value || null }, text.emailSaved)) email.accept(submitted, value);
  }
  return <Section title={text.sections[0]}>
    <div className="p-settings__row">
      {!saved || replacing ? <Field id="jev-key" label={text.key} help={text.keyHelp} error={keyError}>
        <Input ref={input} type="password" autoComplete="off" spellCheck={false} placeholder={text.keyPlaceholder}
          aria-label={text.key} data-secret-input maxLength={KEY_MAX * 2} disabled={state.busy === "secrets.set"} onInput={() => setKeyError(undefined)} />
      </Field> : <div><strong>{text.key}</strong><p className="p-settings__help">{text.keyHelp}</p></div>}
      <div className="p-settings__actions">
        {saved && <StatusTag tone="ok">{text.saved}</StatusTag>}
        {!saved || replacing ? <Button variant="primary" disabled={!!state.busy} loading={state.busy === "secrets.set"} onClick={() => void saveKey()}>{text.saveKey}</Button>
          : <Button ref={replaceButton} disabled={!!state.busy} onClick={() => setReplacing(true)}>{text.replace}</Button>}
        {replacing && <Button disabled={!!state.busy} onClick={() => { if (input.current) input.current.value = ""; setReplacing(false); }}>{text.cancel}</Button>}
        {saved && <Button variant="danger" disabled={!!state.busy} onClick={() => setConfirming(true)}>{text.clear}</Button>}
      </div>
    </div>
    {!saved && <Banner tone="warn" text={text.keyMissing} />}
    <form className="p-settings__row" onSubmit={event => { event.preventDefault(); void saveEmail(); }} noValidate>
      <Field id="sec-email" label={text.email} help={text.emailHelp} error={emailError}>
        <Input value={email.value} placeholder={text.emailPlaceholder} autoComplete="email"
          onChange={event => { email.edit(event.target.value); setEmailError(undefined); }} />
      </Field>
      <Button type="submit" variant="primary" disabled={!!state.busy}>{text.saveEmail}</Button>
    </form>
    {!state.settings!.secContactEmail && <Banner tone="warn" text={text.emailMissing} />}
    <Modal open={confirming} titleId="clear-key-title" onClose={() => { if (!state.busy) setConfirming(false); }}>
      <h2 id="clear-key-title">{text.clearKey}</h2><p>{text.clearKeyHelp}</p>
      {state.error && <Banner tone="danger" text={state.error} />}
      <div className="p-settings__actions">
        <Button disabled={!!state.busy} onClick={() => setConfirming(false)}>{text.cancel}</Button>
        <Button variant="danger" loading={state.busy === "secrets.clear"} disabled={!!state.busy}
          onClick={() => void state.clearKey().then(ok => { if (ok) { pendingFocus.current = "input"; setConfirming(false); } })}>{text.confirmClear}</Button>
      </div>
    </Modal>
  </Section>;
}
