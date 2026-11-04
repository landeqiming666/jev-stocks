import { RpcError, type RpcClient, type PaperOrder, type ParamsOf } from "../../rpc";
import { trading as t } from "../../i18n/zh-CN/trading";

export type PlaceOrderInput = Omit<ParamsOf<"paper.order.place">, "accountId" | "idempotencyKey">;
export type PendingIntent = { params: ParamsOf<"paper.order.place">; uncertain: boolean; running?: Promise<PaperOrder> };
export class OrderIntents {
  private pending = new Map<string, PendingIntent>();
  constructor(private client: RpcClient) {}
  get(accountId: string) { return this.pending.get(accountId) ?? null; }
  place(accountId: string, input: PlaceOrderInput, signal?: AbortSignal): Promise<PaperOrder> {
    let intent = this.pending.get(accountId);
    if (intent && Object.entries(input).some(([key, value]) => intent!.params[key as keyof PlaceOrderInput] !== value))
      return Promise.reject(new RpcError("CONFLICT", t.intentConflict));
    if (intent?.running) return intent.running;
    if (!intent) {
      intent = { params: { ...input, accountId, idempotencyKey: crypto.randomUUID() }, uncertain: false };
      this.pending.set(accountId, intent);
    }
    const current = intent;
    async function resolveOrder(order: PaperOrder) {
      if (order.status === "rejected") throw new RpcError("ORDER_REJECTED", order.rejectReason?.message ?? t.failed, false,
        { orderId: order.orderId, reason: order.rejectReason?.code });
      return order;
    }
    const run = async () => {
      try {
        if (current.uncertain) {
          const page = await this.client.call("paper.orders", { accountId, idempotencyKey: current.params.idempotencyKey }, { signal });
          const stored = page.items.find(order => order.idempotencyKey === current.params.idempotencyKey);
          if (stored) { this.pending.delete(accountId); return await resolveOrder(stored); }
        }
        // 发出后直到响应确认都视为不确定；取消本地等待不能证明后端未写入。
        current.uncertain = true;
        const order = await this.client.call("paper.order.place", current.params, { signal });
        this.pending.delete(accountId);
        return await resolveOrder(order);
      } catch (error) {
        if (error instanceof RpcError && ["ORDER_REJECTED", "INVALID_ARGUMENT", "NOT_FOUND", "CONFLICT"].includes(error.code)) this.pending.delete(accountId);
        throw error;
      } finally { current.running = undefined; }
    };
    current.running = run();
    return current.running;
  }
}
const managers = new WeakMap<RpcClient, OrderIntents>();
export function getOrderIntents(client: RpcClient) {
  let manager = managers.get(client);
  if (!manager) { manager = new OrderIntents(client); managers.set(client, manager); }
  return manager;
}
