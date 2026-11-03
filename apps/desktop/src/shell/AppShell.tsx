import { useEffect, type ReactNode } from "react";
import { useAppStore } from "../app/store";
import { common } from "../i18n/zh-CN";
import { navigate, useRoute } from "../router/useRoute";
import { NavRail } from "./NavRail";
import { PageFrame } from "./PageFrame";
import { StartupFailure } from "./StartupFailure";
import { StatusBar } from "./StatusBar";
import { TopBar } from "./TopBar";

export function AppShell({ children, onRetry, globalFeedback = false }: { children: ReactNode; onRetry?: () => void; globalFeedback?: boolean }) {
  const { route } = useRoute();
  const boot = useAppStore(state => state.bootstrap);
  const market = useAppStore(state => state.dataStatus?.market);
  const offline = useAppStore(state => state.dataStatus?.offline ?? state.bootstrap.value?.offline);
  const ui = useAppStore(state => state.ui);
  const dismiss = useAppStore(state => state.dismissEngineNotice);
  useEffect(() => {
    if (market) document.documentElement.dataset.market = market;
    else delete document.documentElement.dataset.market;
  }, [market]);
  const unconfigured = boot.value && (!boot.value.configured.jevKey || !boot.value.configured.secEmail);
  return <div className="l-app" data-route={route} data-ready={boot.status === "ready"}>
    <TopBar /><NavRail route={route} />
    <div className="l-body">
      <div className="l-banners">
        {boot.status === "ready" && unconfigured && route !== "settings" && <div className="l-notice" role="status">
          <span>{common.configurationRequiredFor(boot.value!.configured)}</span><button className="l-action l-action--secondary" onClick={() => navigate("settings")}>{common.goSettings}</button>
        </div>}
        {offline && !globalFeedback && <div className="l-notice" role="status">{common.offlineNotice}</div>}
        {ui.engineNotice && <div className="l-notice" role="status">
          <span>{common.engineChanged}</span><button className="l-action l-action--secondary" onClick={dismiss}>{common.dismiss}</button>
        </div>}
        {ui.sourceDegraded && <div className="l-notice" role="status">{common.sourceDegraded}</div>}
      </div>
      {boot.status === "ready" ? children : <PageFrame>
        {boot.status === "failed" ? <StartupFailure error={boot.error} onRetry={onRetry} /> :
          <p className="l-startup" role="status">{common.starting}</p>}
      </PageFrame>}
    </div>
    <StatusBar /><div id="feedback-root" />
  </div>;
}
