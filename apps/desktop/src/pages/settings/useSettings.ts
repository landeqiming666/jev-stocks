import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import { notifyToast } from "../../app/events";
import type { ParamsOf, RpcClient, Settings } from "../../rpc";
import type { TestConnectionResult } from "../../rpc/generated/types";
import { errorCodeOf } from "../../lib/errors";
import { settings as text } from "../../i18n/zh-CN/settings";

export type SettingsPatch = ParamsOf<"settings.update">;
type Session = { client: RpcClient; controller: AbortController; read: number; config: number; test: number; writing: boolean };
function safeMessage(error: unknown, demo = false) {
  const code = errorCodeOf(error);
  if (demo && code === "CONFLICT") return text.demoConflict;
  return code && Object.hasOwn(text.errors, code) ? text.errors[code as keyof typeof text.errors] : text.unavailable;
}
function toast(message: string) {
  notifyToast("success", message);
}
export function useSettings() {
  const client = useAppStore(state => state.client);
  const bootstrap = useAppStore(state => state.bootstrap.value);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [secretStatus, setSecretStatus] = useState<{ jevKey: boolean } | null>(null);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null), [testing, setTesting] = useState(false);
  const [connection, setConnection] = useState<TestConnectionResult | null>(null);
  const session = useRef<Session | null>(null);
  const current = (s: Session) => session.current === s && !s.controller.signal.aborted && useAppStore.getState().client === s.client;
  const refresh = useCallback(async () => {
    const s = session.current;
    if (!s || !current(s) || s.writing) return;
    const revision = ++s.read, config = ++s.config;
    s.test++; setConnection(null); setTesting(false);
    setLoading(true); setError(null);
    try {
      const options = { signal: s.controller.signal };
      const [value, status, boot] = await Promise.all([
        s.client.call("settings.get", {}, options), s.client.call("secrets.status", {}, options),
        s.client.call("app.bootstrap", {}, options),
      ]);
      if (!current(s) || revision !== s.read || config !== s.config) return;
      setSettings(value); setSecretStatus(status);
      useAppStore.setState({ bootstrap: { status: "ready", value: boot, error: null } });
    } catch (cause) {
      if (current(s) && revision === s.read && config === s.config) setError(safeMessage(cause));
    } finally { if (current(s) && revision === s.read) setLoading(false); }
  }, []);
  useEffect(() => {
    setSettings(null); setSecretStatus(null); setConnection(null); setBusy(null); setTesting(false);
    if (!client) { setLoading(false); return; }
    const s: Session = { client, controller: new AbortController(), read: 0, config: 0, test: 0, writing: false };
    session.current = s;
    void refresh();
    return () => { s.controller.abort(); if (session.current === s) session.current = null; };
  }, [client, refresh]);

  async function write(action: string, perform: (s: Session) => Promise<void>, message: string) {
    const s = session.current;
    if (!s || !current(s) || s.writing) return false;
    s.writing = true; s.config++; s.read++; s.test++;
    setBusy(action); setError(null); setConnection(null); setTesting(false); setLoading(false);
    let accepted = false;
    try {
      await perform(s);
      if (!current(s)) return false;
      accepted = true;
      const boot = await s.client.call("app.bootstrap", {}, { signal: s.controller.signal });
      if (!current(s)) return false;
      useAppStore.setState({ bootstrap: { status: "ready", value: boot, error: null } });
      toast(message);
    } catch (cause) {
      if (current(s)) setError(accepted ? text.refreshFailed : action === "demo.clear" ? text.demoClearFailed : safeMessage(cause, action === "demo.load"));
    } finally { if (current(s)) { s.writing = false; setBusy(null); } }
    return current(s) && accepted;
  }
  const update = (patch: SettingsPatch, message: string) => write("settings.update", async s => {
    const value = await s.client.call("settings.update", patch, { signal: s.controller.signal });
    if (current(s)) setSettings(value);
  }, message);
  const saveKey = (value: string, clearLocal: () => void) => write("secrets.set", async s => {
    await s.client.call("secrets.set", { name: "jevKey", value }, { signal: s.controller.signal });
    if (current(s)) { clearLocal(); setSecretStatus({ jevKey: true }); }
  }, text.keySaved);
  const clearKey = () => write("secrets.clear", async s => {
    await s.client.call("secrets.clear", { name: "jevKey" }, { signal: s.controller.signal });
    if (current(s)) setSecretStatus({ jevKey: false });
  }, text.keyCleared);
  const demo = (action: "demo.load" | "demo.clear") => write(action, async s => {
    await s.client.call(action, {}, { signal: s.controller.signal });
    if (!current(s)) return;
    setSettings(value => value && { ...value, demoDataLoaded: action === "demo.load" });
  }, action === "demo.load" ? text.demoLoaded : text.demoNotLoaded);
  async function testConnection() {
    const s = session.current;
    if (!s || !current(s) || s.writing) return;
    const revision = ++s.test, config = s.config;
    setTesting(true); setConnection(null); setError(null);
    try {
      const value = await s.client.call("settings.testConnection", {}, { signal: s.controller.signal });
      if (current(s) && revision === s.test && config === s.config) setConnection(value);
    } catch (cause) {
      if (current(s) && revision === s.test && config === s.config) setError(safeMessage(cause));
    } finally { if (current(s) && revision === s.test) setTesting(false); }
  }
  return { settings, secretStatus, bootstrap, loading, busy, error, testing, connection,
    refresh, update, saveKey, clearKey, demo, testConnection };
}
export type SettingsController = ReturnType<typeof useSettings>;
