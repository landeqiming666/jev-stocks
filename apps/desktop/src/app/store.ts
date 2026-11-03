import { create } from "zustand";
import type { Bootstrap, DataStatus, ParamsOfNotification, RpcClient, RpcError } from "../rpc";

export interface AppState {
  bootstrap: { status: "idle" | "starting" | "ready" | "failed"; value: Bootstrap | null; error: RpcError | null };
  client: RpcClient | null;
  ui: { drawerOpen: boolean; engineNotice: boolean; sourceDegraded: boolean };
  dataStatus: DataStatus | null;
  budget: ParamsOfNotification<"budget.updated"> | null;
  scanProgress: ParamsOfNotification<"scan.progress"> | null;
  dataAsOf: string | null;
  lastSuccessfulScanAt: string | null;
  setDrawerOpen: (open: boolean) => void;
  setDataStatus: (value: DataStatus | null, asOf?: string) => void;
  setBudget: (value: AppState["budget"]) => void;
  setScanProgress: (value: AppState["scanProgress"]) => void;
  setLastSuccessfulScanAt: (value: string | null) => void;
  dismissEngineNotice: () => void;
  reset: () => void;
}
export const initialState = () => ({
  bootstrap: { status: "idle" as const, value: null, error: null }, client: null,
  ui: { drawerOpen: false, engineNotice: false, sourceDegraded: false },
  dataStatus: null, budget: null, scanProgress: null, dataAsOf: null, lastSuccessfulScanAt: null,
});
export const useAppStore = create<AppState>(set => ({
  ...initialState(),
  setDrawerOpen: drawerOpen => set(state => ({ ui: { ...state.ui, drawerOpen } })),
  setDataStatus: (dataStatus, asOf) => set({ dataStatus, budget: dataStatus?.budget ?? null, dataAsOf: asOf ?? null }),
  setBudget: budget => set({ budget }),
  setScanProgress: scanProgress => set({ scanProgress }),
  setLastSuccessfulScanAt: lastSuccessfulScanAt => set({ lastSuccessfulScanAt }),
  dismissEngineNotice: () => set(state => ({ ui: { ...state.ui, engineNotice: false } })),
  reset: () => set(initialState()),
}));
