import { Banner, Button, Radio, StatusTag } from "../../components/ui";
import { settings as text } from "../../i18n/zh-CN/settings";
import type { EngineChoice } from "../../rpc";
import type { SettingsController } from "./useSettings";
import { useDraft } from "./useDraft";
import { Section } from "./Section";

export const CHECK_ORDER = ["Jev", "SEC", "JEVDB"] as const;
export function EngineSection({ state }: { state: SettingsController }) {
  const choice = useDraft(state.settings!.engine), boot = state.bootstrap;
  const blocked = choice.value === "jevdb" && !boot?.engine.jevdbAvailable;
  const result = state.connection;
  const usable = result?.ok && result.engine !== null && !blocked;
  return <Section title={text.sections[1]}>
    <fieldset className="p-settings__engines" aria-label={text.sections[1]} aria-busy={state.busy === "settings.update"}>
      {(Object.keys(text.engineChoices) as EngineChoice[]).map(value => <Radio key={value} name="settings-engine" value={value}
        checked={choice.value === value} label={text.engineChoices[value]} hint={text.engineHints[value]} onChange={next => {
          if (state.busy) return;
          choice.edit(next);
          void state.update({ engine: next as EngineChoice }, text.engineSaved).then(ok => { if (ok) choice.accept(next); });
        }} />)}
    </fieldset>
    <div className="p-settings__row">
      <div><p>{text.currentEngine} <StatusTag tone={boot?.engine.active ? "info" : "warn"}>
        {boot?.engine.active ? text.engineChoices[boot.engine.active] : text.noEngine}</StatusTag></p>
        <p>{text.model} <span className="u-mono">{state.settings!.modelId}</span></p>
        <p className="p-settings__help">{text.modelHelp} · {text.testHelp}</p></div>
      <Button loading={state.testing} disabled={!!state.busy} onClick={() => void state.testConnection()}>{text.test}</Button>
    </div>
    {blocked && <Banner tone="warn" text={text.jevdbUnavailable} />}
    {result && <div aria-live="polite">
      <ul className="p-settings__checks" aria-label={text.checks}>{CHECK_ORDER.map(name => {
        const check = result.checks.find(item => item.name === name)!;
        return <li key={name}><StatusTag tone={check.ok ? "ok" : "danger"}>{check.ok ? "✓" : "✗"}</StatusTag>
          <strong>{name}</strong><span>{check.message}</span>
          <span className="u-mono">{check.latencyMs === null ? text.noLatency : `${check.latencyMs} ms`}</span></li>;
      })}</ul>
      {!result.checks[2]!.ok && !blocked && <Banner tone="warn" text={text.fallback} />}
      <Banner tone={usable ? "info" : "danger"} text={usable ? text.usable : text.testFailed} />
    </div>}
  </Section>;
}
