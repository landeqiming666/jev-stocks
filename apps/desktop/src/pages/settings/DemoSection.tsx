import { useState } from "react";
import { Banner, Button, Modal, StatusTag } from "../../components/ui";
import { settings as text } from "../../i18n/zh-CN/settings";
import type { SettingsController } from "./useSettings";
import { Section } from "./Section";
export function DemoSection({ state }: { state: SettingsController }) {
  const [confirming, setConfirming] = useState(false), loaded = state.settings!.demoDataLoaded;
  return <Section title={text.sections[4]}><div className="p-settings__row">
    <div><StatusTag tone={loaded ? "info" : "none"}>{loaded ? text.demoLoaded : text.demoNotLoaded}</StatusTag><p className="p-settings__help">{text.demoHelp}</p></div>
    <div className="p-settings__actions"><Button disabled={!!state.busy || loaded} loading={state.busy === "demo.load"}
      disabledReason={text.demoLoaded} onClick={() => void state.demo("demo.load")}>{text.demoLoad}</Button>
      <Button variant="danger" disabled={!!state.busy || !loaded} onClick={() => setConfirming(true)}>{text.demoClear}</Button></div>
  </div><Modal open={confirming} titleId="clear-demo-title" onClose={() => { if (!state.busy) setConfirming(false); }}>
    <h2 id="clear-demo-title">{text.demoClear}</h2><p>{text.demoClearHelp}</p>
    {state.error && <Banner tone="danger" text={state.error} />}
    <div className="p-settings__actions"><Button disabled={!!state.busy} onClick={() => setConfirming(false)}>{text.cancel}</Button>
      <Button variant="danger" disabled={!!state.busy} loading={state.busy === "demo.clear"}
        onClick={() => void state.demo("demo.clear").then(ok => { if (ok) setConfirming(false); })}>{text.confirmClear}</Button></div>
  </Modal></Section>;
}
