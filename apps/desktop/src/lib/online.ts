import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
let online = true;
const read = () => typeof navigator === "undefined" ? true : navigator.onLine;
function change(event: Event) {
  const next = event.type === "online";
  if (next === online) return;
  online = next;
  for (const fn of [...listeners]) fn();
}
export function subscribeOnline(fn: () => void): () => void {
  if (!listeners.size && typeof window !== "undefined") {
    online = read();
    window.addEventListener("online", change);
    window.addEventListener("offline", change);
  }
  const listener = () => fn();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (!listeners.size && typeof window !== "undefined") {
      window.removeEventListener("online", change);
      window.removeEventListener("offline", change);
    }
  };
}
const snapshot = () => listeners.size ? online : read();
export function useOnline(): boolean { return useSyncExternalStore(subscribeOnline, snapshot, () => true); }
