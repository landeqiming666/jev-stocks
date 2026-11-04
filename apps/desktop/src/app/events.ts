export { navigate } from "../router/useRoute";
export const TOAST_EVENT = "sentinel:toast";
export const REFRESH_EVENT = "sentinel:refresh";
export type ToastTone = "success" | "error" | "ok" | "warn" | "danger" | "none" | "info";
export interface ToastDetail { tone: ToastTone; text: string }
export function notifyToast(tone: ToastTone, text: string) {
  window.dispatchEvent(new CustomEvent<ToastDetail>(TOAST_EVENT, { detail: { tone, text } }));
}
export function refresh(scope?: string) {
  window.dispatchEvent(new CustomEvent(REFRESH_EVENT, { detail: { scope } }));
}
