import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { Application } from "../../app/Application";
import { useAppStore } from "../../app/store";
import { getRpcClient, type MockRpcClient } from "../../rpc";
import { settings as text } from "../../i18n/zh-CN/settings";
import { feedbackRootOptions } from "../../lib/errors";
import { useRoute } from "../../router/useRoute";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";

if (!import.meta.env.DEV || import.meta.env.VITE_RPC !== "mock") throw new Error("Mock development entry required");
function createClient() {
  const client = getRpcClient() as MockRpcClient;
  const query = new URLSearchParams(window.location.hash.split("?")[1]);
  const unconfigured = query.get("state") === "unconfigured";
  client.setExample("settings.get", unconfigured ? "unconfigured" : "configured");
  client.setExample("app.bootstrap", unconfigured ? "unconfigured" : "ready");
  client.setExample("secrets.status", unconfigured ? "none" : "configured");
  client.setExample("settings.testConnection", query.get("state") === "test-failed" ? "failed" : "ok");
  client.setExample("settings.update", "ok");
  client.setExample("secrets.set", "ok"); client.setExample("secrets.clear", "ok");
  client.setExample("demo.load", "ok"); client.setExample("demo.clear", "ok");
  return client;
}
function Replay() {
  const ready = useAppStore(state => state.bootstrap.status === "ready"), { params } = useRoute();
  const scenario = params.get("state");
  useEffect(() => {
    if (!ready || (scenario !== "test-ok" && scenario !== "test-failed")) return;
    // 陈列只触发真实页面按钮；结果仍由已有 mock RPC 的契约示例返回。
    const timer = window.setTimeout(() => {
      [...document.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === text.test)?.click();
    }, 100);
    return () => window.clearTimeout(timer);
  }, [ready, scenario]);
  return null;
}
function Gallery() {
  const { params } = useRoute();
  return <><div className="p-settings__gallery-note">{text.mock}</div>
    <Application key={params.get("state")} createClient={createClient} /><Replay /></>;
}
createRoot(document.getElementById("root")!, feedbackRootOptions).render(<StrictMode><Gallery /></StrictMode>);
