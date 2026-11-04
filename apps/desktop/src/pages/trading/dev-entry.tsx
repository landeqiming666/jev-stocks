import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { useAppStore } from "../../app/store";
import { FeedbackHost } from "../../components/feedback";
import { trading as t } from "../../i18n/zh-CN/trading";
import { RpcError, type Bootstrap, type PaperOrder, type Portfolio } from "../../rpc";
import { MOCK_EXAMPLES } from "../../rpc/generated/mock-data";
import { RouterView } from "../../router/RouterView";
import { AppShell } from "../../shell/AppShell";
import { fakeClient, instrument, orders, pending, portfolio } from "./test-support";
import "../../styles/tokens.css";
import "../../styles/base.css";
import "../../styles/layout.css";
import "../../styles/platform-macos.css";

if (!import.meta.env.DEV || import.meta.env.VITE_RPC !== "mock") throw new Error("Mock development entry required");
const state = new URLSearchParams(window.location.hash.split("?")[1]).get("state") ?? "default";
let current: Portfolio = structuredClone(portfolio);
current.account.clockDate = "2026-10-29"; current.account.startDate = "2026-10-29"; current.asOf = "2026-10-29";
let currentOrders: PaperOrder[] = structuredClone(orders).map(order => ({ ...order, createdClockDate: "2026-10-29" }));
let accounts = state === "no_account" ? [] : [current.account];
let attempts = 0, sequence = 0;
if (state === "new_account") {
  current = { ...current, cash: "100000.0000", reservedCash: "0.0000", availableCash: "100000.0000", equity: "100000.0000", positions: [], pendingOrders: 0 };
  currentOrders = [];
}
const fake = fakeClient((method, params) => {
  if (method === "paper.accounts") return { items: accounts };
  if (method === "paper.portfolio") return structuredClone(current);
  if (method === "paper.orders") return { items: currentOrders.filter(order => !params.idempotencyKey || order.idempotencyKey === params.idempotencyKey), nextCursor: null };
  if (method === "instruments.search") return { items: params.query === "qqqq" ? [] : [instrument] };
  if (method === "paper.createAccount") {
    const account = { ...current.account, accountId: `synthetic-account-${++sequence}`, name: String(params.name), initialCash: String(params.initialCash), startDate: String(params.startDate), clockDate: String(params.startDate) };
    current = { ...current, account, cash: account.initialCash + (account.initialCash.includes(".") ? "" : ".0000"), reservedCash: "0.0000", availableCash: account.initialCash, equity: account.initialCash, positions: [], pendingOrders: 0 };
    accounts = [...accounts, account]; currentOrders = []; return account;
  }
  if (method === "paper.order.place") {
    const order: PaperOrder = { ...pending, orderId: `synthetic-order-${++sequence}`, accountId: current.account.accountId,
      idempotencyKey: String(params.idempotencyKey), quantity: Number(params.quantity), side: params.side as "buy" | "sell", createdClockDate: current.account.clockDate };
    if (state === "error-cash" || state === "error-position") {
      order.status = "rejected"; order.reservedCash = null; order.estimate = null;
      order.rejectReason = { code: state === "error-cash" ? "INSUFFICIENT_CASH" : "INSUFFICIENT_POSITION",
        message: state === "error-cash" ? t.demoCash : t.demoPosition };
      currentOrders.unshift(order);
      throw new RpcError("ORDER_REJECTED", order.rejectReason.message, false, { orderId: order.orderId, reason: order.rejectReason.code });
    }
    if (state === "timeout" && ++attempts === 1)
      return new Promise((_resolve, reject) => setTimeout(() => reject(new RpcError("TIMEOUT", t.demoTimeout, true)), 100));
    currentOrders.unshift(order); return order;
  }
  if (method === "paper.order.cancel") {
    const order = currentOrders.find(order => order.orderId === params.orderId)!;
    order.status = "cancelled"; order.reservedCash = null; return order;
  }
  if (method === "paper.advance") {
    if (state === "no-price" || current.account.clockDate === "2026-10-30")
      throw new RpcError("DATA_INSUFFICIENT", t.demoNoPrice, false, { nextDay: current.account.clockDate === "2026-10-30" ? "2026-11-02" : "2026-10-30" });
    const filled = currentOrders.filter(order => order.status === "pending").map(order => ({ ...order, status: "filled" as const, reservedCash: null,
      fills: [{ fillId: `synthetic-fill-${++sequence}`, filledOn: "2026-10-30", price: "28.564275", quantity: order.quantity, amount: "2856.4275", fee: "0.0000" }] }));
    currentOrders = [...filled, ...currentOrders.filter(order => order.status !== "pending")];
    current = { ...current, account: { ...current.account, clockDate: "2026-10-30" }, asOf: "2026-10-30", reservedCash: "0.0000", pendingOrders: 0 };
    accounts = accounts.map(account => account.accountId === current.account.accountId ? current.account : account);
    return { clockDate: "2026-10-30", tradingDay: true, filled, rejected: [], pendingRemaining: 0, portfolio: current };
  }
  if (method === "paper.reset") {
    if (state === "reset-failure") throw new RpcError("INTERNAL", t.demoBackup, true, { reason: "PAPER_BACKUP_FAILED" });
    currentOrders = []; current = { ...current, positions: [], account: { ...current.account, clockDate: current.account.startDate }, cash: "100000.0000",
      reservedCash: "0.0000", availableCash: "100000.0000", equity: "100000.0000", pendingOrders: 0 };
    return { ok: true };
  }
});
const bootstrap = structuredClone(MOCK_EXAMPLES["app.bootstrap"][0]!.result) as unknown as Bootstrap;
bootstrap.configured = { jevKey: false, secEmail: false };
bootstrap.now = "2026-10-29T12:00:00Z";
useAppStore.setState({ client: fake.client, bootstrap: { status: "ready", value: bootstrap, error: null } });
declare global { interface Window { u05Calls: typeof fake.calls; } }
window.u05Calls = fake.calls;
document.documentElement.dataset.platform = "macos";
createRoot(document.getElementById("root")!).render(<StrictMode><AppShell globalFeedback>
  <FeedbackHost coreStatusListener={async () => () => {}}><RouterView /></FeedbackHost>
</AppShell><span className="u-visually-hidden">{t.fixture}</span></StrictMode>);
