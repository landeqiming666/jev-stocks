import { common } from "../i18n/zh-CN";

export const ROUTES = ["today", "holdings", "trading", "risk", "scan", "settings"] as const;
export type Route = typeof ROUTES[number];
export const DEFAULT_ROUTE: Route = "today";
export const navigation = ROUTES.map(route => ({ route, label: common.nav[route] }));
export interface RouteState { route: Route; params: URLSearchParams }
