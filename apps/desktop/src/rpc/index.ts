import { createRpcClient } from "./client";
import { createMockRpcClient } from "./mock/client";

export { createRpcClient, DEFAULT_TIMEOUT_MS, CONNECTION_TIMEOUT_MS, EXPORT_TIMEOUT_MS } from "./client";
export type { RpcClient, RpcClientOptions, RpcTransport, CoreStatus, CallOptions } from "./client";
export { RpcError } from "./errors";
export { createMockRpcClient } from "./mock/client";
export type { MockRpcClient } from "./mock/client";
export type * from "./generated/methods";
export type { ErrorCode, Instrument, Holding, Thesis, ThesisVersionItem, DecisionSummary, DecisionDetail,
  Inbox, ScanRun, ScanBatch, PaperAccount, PaperOrder, Portfolio, RiskResult, Settings, Bootstrap,
  Decimal, IsoDate, IsoTime, Market, Relation, Engine, EngineChoice, ActionType, Evidence,
  Probabilities, EventRef, ActionRecord, DataStatus, Fill, Position } from "./generated/types";

export const MOCK_ENV = "mock";
export function getRpcClient(): import("./client").RpcClient {
  return import.meta.env.VITE_RPC === MOCK_ENV ? createMockRpcClient({}) : createRpcClient();
}
