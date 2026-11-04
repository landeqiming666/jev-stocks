import { forwardRef } from "react";
import { common } from "../../i18n/zh-CN/common";

export interface MarketBadgeProps { market: "us" | "cn" | "hk"; }
export const MarketBadge = forwardRef<HTMLSpanElement, MarketBadgeProps>(function MarketBadge({ market }, ref) {
  return <span ref={ref} className="c-market">{common.market[market]}</span>;
});
