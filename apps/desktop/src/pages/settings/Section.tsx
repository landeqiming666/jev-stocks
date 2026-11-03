import type { ReactNode } from "react";
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="c-card p-settings__group" aria-label={title}><h2>{title}</h2>{children}</section>;
}
