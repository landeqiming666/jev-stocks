import { forwardRef } from "react";
import { common } from "../../i18n/zh-CN/common";
import { formatProbability } from "../../app/format";

export interface ProbabilityProps { value: number; }

export const Probability = forwardRef<HTMLSpanElement, ProbabilityProps>(function Probability({ value }, ref) {
  return <span ref={ref} className="c-prob" title={common.probabilityTitle}>{formatProbability(value)}</span>;
});
