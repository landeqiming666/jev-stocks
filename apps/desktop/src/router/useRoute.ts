import { useSyncExternalStore } from "react";
import { buildHash, parseHash } from "./hash";
import type { Route } from "./routes";

export const ROUTE_EVENT = "sentinel:navigate";
function subscribe(handler: () => void) {
  const events = ["hashchange", "popstate", ROUTE_EVENT];
  events.forEach(event => window.addEventListener(event, handler));
  return () => events.forEach(event => window.removeEventListener(event, handler));
}
export function useRoute() {
  return parseHash(useSyncExternalStore(subscribe, () => window.location.hash, () => "#/today"));
}
export function navigate(route: Route, params?: Record<string, string>, opts?: { replace?: boolean }) {
  window.history[opts?.replace ? "replaceState" : "pushState"](null, "", buildHash(route, params));
  window.dispatchEvent(new Event(ROUTE_EVENT));
  document.querySelector(".l-main")?.scrollTo?.({ top: 0, left: 0, behavior: "instant" });
}
