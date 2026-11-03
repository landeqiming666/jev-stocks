import { DEFAULT_ROUTE, ROUTES, type Route, type RouteState } from "./routes";

export function parseHash(hash: string): RouteState {
  const raw = hash.replace(/^#\/?/, "");
  const split = raw.indexOf("?");
  const path = split < 0 ? raw : raw.slice(0, split);
  const route = ROUTES.find(route => route === path) ?? DEFAULT_ROUTE;
  return { route, params: new URLSearchParams(split < 0 ? "" : raw.slice(split + 1)) };
}
export function buildHash(route: Route, params?: Record<string, string>): string {
  const query = new URLSearchParams(params).toString();
  return `#/${route}${query ? "?" + query : ""}`;
}
