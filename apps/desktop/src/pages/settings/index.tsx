import { Banner, Button, Skeleton } from "../../components/ui";
import { PageFrame } from "../../shell/PageFrame";
import { settings as text } from "../../i18n/zh-CN/settings";
import { useSettings } from "./useSettings";
import { SecretsSection } from "./SecretsSection";
import { EngineSection } from "./EngineSection";
import { BudgetSection } from "./BudgetSection";
import { PrivacySection } from "./PrivacySection";
import { DemoSection } from "./DemoSection";
import { AboutSection } from "./AboutSection";
import "./settings.css";

export default function SettingsPage() {
  const state = useSettings();
  const available = state.settings && state.secretStatus;
  return <PageFrame><div className="p-settings">
    <header className="p-settings__head"><h1>{text.title}</h1>
      <Button disabled={!!state.busy} loading={state.loading} onClick={() => void state.refresh()}>{text.refresh}</Button></header>
    {state.error && <Banner tone="danger" text={state.error} action={<Button disabled={!!state.busy} onClick={() => void state.refresh()}>{text.retry}</Button>} />}
    {available ? <>
      {(!state.secretStatus!.jevKey || !state.settings!.secContactEmail) && <Banner tone="info" text={text.configuration} />}
      <SecretsSection state={state} /><EngineSection state={state} /><BudgetSection state={state} />
      <PrivacySection settings={state.settings!} /><DemoSection state={state} /><AboutSection bootstrap={state.bootstrap} />
    </> : state.loading ? <Skeleton rows={6} /> : <Banner tone="warn" text={text.unavailable} />}
  </div></PageFrame>;
}
