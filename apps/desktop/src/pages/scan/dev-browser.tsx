import { StrictMode, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Application } from "../../app/Application";
import { RouterView } from "../../router/RouterView";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { Menu } from "../../components/ui/Menu";
import { createMockRpcClient, RpcError, type MockRpcClient, type ScanRun, type ResultOf } from "../../rpc";
import { MOCK_EXAMPLES } from "../../rpc/generated/mock-data";
import history from "./__fixtures__/history.json";
import detail from "./__fixtures__/detail.json";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";
import "../../components/ui/components.css";

if (!import.meta.env.DEV || import.meta.env.VITE_RPC !== "mock") throw new Error("U-04 fixtures require DEV and VITE_RPC=mock");
declare global {
  interface Window {
    __scanBrowser: {
      calls: { method: string; params: unknown }[];
      progress: (done: number, total: number) => void;
      finish: (status: ScanRun["status"]) => void;
      retryFailure: (enabled: boolean) => void;
    };
  }
}
// 此独立入口只回放合约 fixture；生产组合根不导入它。
function createFixtureClient(): MockRpcClient {
  const base = createMockRpcClient({ scenario: "scan.default", warn: () => {} });
  let currentDetail = structuredClone(detail) as ResultOf<"scan.detail">;
  let currentHistory: ResultOf<"scan.history"> | null = null;
  let failRetry = false;
  const calls: { method: string; params: unknown }[] = [];
  const runningHistory = () => structuredClone(MOCK_EXAMPLES["scan.history"].find(item => item.name === "running")!.result) as unknown as ResultOf<"scan.history">;
  const client: MockRpcClient = {
    ...base,
    async call(method, params, options) {
      calls.push({ method, params });
      if (method === "scan.retryBatch" && failRetry) throw new RpcError("MODEL_ERROR", "synthetic browser retry: Jev 529", true);
      const response = await base.call(method, params, options);
      let value: unknown = response;
      if (method === "scan.start") currentHistory = runningHistory();
      if (method === "scan.history" && currentHistory) value = currentHistory;
      if (method === "scan.status") value = (currentHistory ?? history).items.find(run => run.runId === (params as { runId: string }).runId) ?? response;
      if (method === "scan.detail") {
        const id = (params as { runId: string }).runId;
        value = id === currentDetail.run.runId ? currentDetail : { run: (currentHistory ?? history).items.find(run => run.runId === id), batches: [] };
      }
      if (method === "scan.retryBatch") {
        const batch = response as ResultOf<"scan.retryBatch">;
        currentDetail = { ...currentDetail, batches: currentDetail.batches.map(item => item.batchId === batch.batchId ? batch : item) };
      }
      return structuredClone(value) as ResultOf<typeof method>;
    },
  };
  window.__scanBrowser = {
    calls,
    progress(done, total) {
      currentHistory ??= runningHistory();
      base.injectNotification("scan.progress", { runId: currentHistory.items[0]!.runId, market: "us", stage: "decide", done, total, message: "正在判定 ZZCL 的 6-K" });
    },
    finish(status) {
      currentHistory ??= runningHistory();
      const run = { ...currentHistory.items[0]!, status };
      currentHistory = { ...currentHistory, items: [run, ...currentHistory.items.slice(1)] };
      base.injectNotification("scan.finished", run);
    },
    retryFailure(enabled) { failRetry = enabled; },
  };
  return client;
}
function Layers() {
  const [modal, setModal] = useState(false), [menu, setMenu] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return <div style={{ position: "fixed", left: 90, bottom: 36, zIndex: 10 }}>
    <Button ref={trigger} id="fixture-menu" onClick={() => setMenu(true)}>Fixture menu</Button>
    <Button onClick={() => setModal(true)}>Fixture modal</Button>
    {menu && <Menu triggerRef={trigger} onClose={() => setMenu(false)} onSelect={() => {}}
      items={[{ id: "fixture", label: "Fixture item" }]} />}
    <Modal open={modal} titleId="fixture-modal-title" onClose={() => setModal(false)}>
      <h2 id="fixture-modal-title">Fixture modal title</h2><Button onClick={() => setModal(false)}>取消</Button>
    </Modal>
  </div>;
}
const layers = new URLSearchParams(window.location.search).has("layers");
createRoot(document.getElementById("root")!).render(<StrictMode>
  <Application createClient={createFixtureClient} view={<><RouterView />{layers && <Layers />}</>} />
</StrictMode>);
