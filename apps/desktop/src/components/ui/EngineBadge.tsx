import { forwardRef } from "react";
import { common } from "../../i18n/zh-CN/common";
import { Icon } from "./Icon";

export interface EngineBadgeProps {
  active: "jevdb" | "jev_direct" | null;
  modelId: string;
  state: "ok" | "degraded" | "unconfigured";
}

export const EngineBadge = forwardRef<HTMLSpanElement, EngineBadgeProps>(function EngineBadge({
  active, modelId, state,
}, ref) {
  const degraded = state === "degraded";
  const label = !active || state === "unconfigured" ? common.engine.unconfigured : common.engine[active];
  return <span ref={ref} data-ui className={`c-engine${degraded ? " is-degraded" : ""}`}
    title={degraded ? common.engineDegradedTitle : common.engineTitle}>
    {degraded && <Icon name="info" />}{label}{modelId ? ` · ${modelId}` : ""}
  </span>;
});
