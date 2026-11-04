import { common } from "../i18n/zh-CN";
import { MOCK_ENV } from "../rpc";
import { formatDateTime } from "../app/format";
import { useAppStore } from "../app/store";

export function TopBar() {
  const value = useAppStore(state => state.bootstrap.value);
  const data = useAppStore(state => state.dataStatus);
  const preview = import.meta.env.VITE_RPC === MOCK_ENV;
  const engine = data?.engine ?? value?.engine;
  const active = engine?.active;
  const offline = data?.offline ?? value?.offline;
  const market = data ? `${common.market[data.market]} ${common.marketState[data.marketState]}${
    data.marketState === "closed" && data.nextOpenAt ? ` · ${common.nextOpen} ${formatDateTime(data.nextOpenAt)}` : ""}` : common.marketUnknown;
  const configured = data ? data.engine.state !== "unconfigured" : value?.configured.jevKey;
  const degraded = data ? data.engine.state === "degraded" : value?.engine.requested !== "jev_direct" &&
    value?.engine.active === "jev_direct" && !value.engine.jevdbAvailable;
  const badge = !engine ? common.engine.unknown : !active || !configured ? common.engine.unconfigured :
    `${common.engine[active]} · ${engine.modelId}${degraded ? " · " + common.engine.degraded : ""}`;
  return <header className="l-top">
    <span className="l-top__brand">{common.appName}</span>
    <span className="l-top__market">{market}</span>
    <span className="l-top__spacer" />
    {preview && <span className="l-preview">{common.preview}</span>}
    {!preview && value?.demoDataLoaded && <span className="l-preview">{common.demoData}</span>}
    {offline && <span className="c-tag c-tag--warn">{common.offline}</span>}
    <span className="c-engine" title={preview ? common.previewEngine : badge}>
      {preview && <span className="u-small">{common.previewEngine} · </span>}{badge}
    </span>
  </header>;
}
