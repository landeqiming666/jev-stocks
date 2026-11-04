import type { ReactNode } from "react";
import { common } from "../i18n/zh-CN";
import { buildHash } from "../router/hash";
import { navigation, type Route } from "../router/routes";

const paths: Record<Route, ReactNode> = {
  today: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></>,
  holdings: <><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" /></>,
  trading: <path d="M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4" />,
  risk: <path d="M22 12h-4l-3 9L9 3l-3 9H2" />,
  scan: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><path d="M12 12 19 5" /></>,
  settings: <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />,
};
export function NavRail({ route, icon }: { route: Route; icon?: (route: Route) => ReactNode }) {
  return <nav className="l-nav" aria-label={common.mainNavigation}>
    {navigation.map(item => <NavItem key={item.route} item={item} route={route} icon={icon} />)}
  </nav>;
}
function NavItem({ item, route, icon }: { item: typeof navigation[number]; route: Route; icon?: (route: Route) => ReactNode }) {
  return <>
      {item.route === "settings" && <span className="l-nav__spacer" />}
      <a className={`l-nav__item${route === item.route ? " is-active" : ""}`} href={buildHash(item.route)}
        aria-current={route === item.route ? "page" : undefined} aria-label={item.label} title={item.label}>
        {icon ? icon(item.route) : <svg className="c-icon c-icon--20" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          {paths[item.route]}
        </svg>}
        <span className="l-nav__label">{item.label}</span>
      </a>
  </>;
}
