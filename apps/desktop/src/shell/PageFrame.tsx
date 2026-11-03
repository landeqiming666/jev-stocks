import type { ReactNode } from "react";

export function PageFrame({ children, aside, asideOpen = false, asideLabel }: {
  children: ReactNode; aside?: ReactNode; asideOpen?: boolean; asideLabel?: string;
}) {
  return <div className={`l-content${asideOpen ? " has-drawer" : ""}`}>
    <main className="l-main" id="main"><div className="l-main__inner">{children}</div></main>
    {asideOpen && <>
      <aside className="l-drawer" aria-label={asideLabel}>{aside}</aside>
      <div className="l-scrim" aria-hidden="true" />
    </>}
  </div>;
}
