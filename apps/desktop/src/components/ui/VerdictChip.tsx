import { forwardRef } from "react";
import { common } from "../../i18n/zh-CN/common";
import { Icon } from "./Icon";
import type { IconName } from "./types";

export type VerdictKind = "overturn" | "weaken" | "support" | "none" | "uncertain";

export interface VerdictChipProps { kind: VerdictKind; }
const meta = {
  overturn: ["over", "alert-triangle"], weaken: ["weak", "arrow-down"],
  support: ["hold", "check"], none: ["none", "minus"], uncertain: ["unsure", "help-circle"],
} satisfies Record<VerdictKind, [string, IconName]>;

export const VerdictChip = forwardRef<HTMLSpanElement, VerdictChipProps>(function VerdictChip({ kind }, ref) {
  const [className, icon] = meta[kind];
  return <span ref={ref} className={`c-verdict c-verdict--${className}`}>
    <Icon name={icon} />{common.verdict[kind]}
  </span>;
});
