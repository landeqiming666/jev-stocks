import { forwardRef, type ReactNode } from "react";
import { Icon } from "./Icon";

export interface BannerProps { tone: "info" | "warn" | "danger"; text: string; action?: ReactNode; }
export const Banner = forwardRef<HTMLDivElement, BannerProps>(function Banner({ tone, text, action }, ref) {
  return <div ref={ref} className={`c-banner c-banner--${tone}`} role={tone === "danger" ? "alert" : "status"}>
    <Icon name={tone === "info" ? "info" : "alert-triangle"} /><div className="c-banner__body">{text}</div>
    {action && <div className="c-banner__actions">{action}</div>}
  </div>;
});
