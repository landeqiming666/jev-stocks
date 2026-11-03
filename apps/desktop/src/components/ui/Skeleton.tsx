import { forwardRef } from "react";
import { common } from "../../i18n/zh-CN/common";

export interface SkeletonProps { rows?: number; }
export const Skeleton = forwardRef<HTMLDivElement, SkeletonProps>(function Skeleton({ rows = 3 }, ref) {
  const count = Number.isFinite(rows) ? Math.max(0, Math.min(100, Math.floor(rows))) : 0;
  return <div ref={ref} className="c-skeleton-stack" aria-busy="true" aria-label={common.loading}>
    {Array.from({ length: count }, (_, index) => <div key={index} className="c-skeleton c-skeleton--card" />)}
  </div>;
});
