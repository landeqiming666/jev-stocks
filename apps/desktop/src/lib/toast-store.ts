import { useSyncExternalStore } from "react";

export type ToastTone = "success" | "error";
export interface ToastItem { id: string; tone: ToastTone; text: string; createdAt: number; }
export const MAX_TOASTS = 3;
export const TOAST_SUCCESS_MS = 4000;
export const DEDUPE_WINDOW_MS = 1000;
let items: ToastItem[] = [];
const listeners = new Set<(items: ToastItem[]) => void>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const copy = () => items.map(item => ({ ...item }));

function publish() {
  for (const fn of [...listeners]) {
    try { fn(copy()); } catch { /* 消费者异常不能阻止其他订阅者或把原文泄露到事件日志。 */ }
  }
}
function cancelTimer(id: string) { clearTimeout(timers.get(id)); timers.delete(id); }
export function pushToast(input: { tone: ToastTone; text: string }): string {
  const now = Date.now();
  const duplicate = items.find(item => item.tone === input.tone && item.text === input.text &&
    now >= item.createdAt && now - item.createdAt < DEDUPE_WINDOW_MS);
  const id = duplicate?.id ?? crypto.randomUUID();
  // 复制对象并刷新组件 key，使 U-01 Toast 的内部计时器也从本次通知重新开始。
  const next = Object.freeze({ ...input, id, createdAt: now });
  items = [...items.filter(item => item.id !== id), next];
  while (items.length > MAX_TOASTS) cancelTimer(items.shift()!.id);
  cancelTimer(id);
  if (input.tone === "success") timers.set(id, setTimeout(() => dismissToast(id), TOAST_SUCCESS_MS));
  publish();
  return id;
}
export function dismissToast(id: string): void {
  cancelTimer(id);
  if (!items.some(item => item.id === id)) return;
  items = items.filter(item => item.id !== id);
  publish();
}
export function getToasts(): ToastItem[] { return copy(); }
export function subscribeToasts(fn: (items: ToastItem[]) => void): () => void {
  const listener = (value: ToastItem[]) => fn(value);
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
const snapshot = () => items;
const empty: ToastItem[] = [];
export function useToasts() { return useSyncExternalStore(subscribeToasts, snapshot, () => empty); }
