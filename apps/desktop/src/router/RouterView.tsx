import { useEffect, type ComponentType } from "react";
import { common } from "../i18n/zh-CN";
import { PageFrame } from "../shell/PageFrame";
import { navigate, useRoute } from "./useRoute";

const pages = import.meta.glob<{ default: ComponentType }>("../pages/*/index.tsx", { eager: true });
export function RouterView({ pageModules = pages }: { pageModules?: typeof pages } = {}) {
  const { route, params } = useRoute();
  const query = params.toString();
  const Page = pageModules[`../pages/${route}/index.tsx`]?.default;
  useEffect(() => {
    const main = document.querySelector<HTMLElement>("main");
    main?.scrollTo?.({ top: 0, left: 0, behavior: "instant" });
    const title = main?.querySelector<HTMLHeadingElement>("h1");
    if (title) { title.tabIndex = -1; title.focus({ preventScroll: true }); }
    document.title = `${common.nav[route]} · ${common.appName}`;
  }, [route, query]);
  return <div className="l-page" key={route}>
    {Page ? <Page /> : <PageFrame>
      <h1 className="u-h1">{common.nav[route]}</h1>
      <section className="l-placeholder">
        <h2 className="u-h2">{common.pageMissing}</h2>
        <p className="u-muted">{common.shellOnly}</p>
        <button className="l-action" onClick={() => navigate(route === "settings" ? "today" : "settings")}>
          {route === "settings" ? common.goToday : common.goSettings}
        </button>
      </section>
    </PageFrame>}
  </div>;
}
