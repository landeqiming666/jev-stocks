import { forwardRef, type ReactNode } from "react";

export interface CardProps { children: ReactNode; }
export const CARD_RADIUS = "10px";
export const CARD_PAD = "20px";
export const Card = forwardRef<HTMLElement, CardProps>(function Card({ children }, ref) {
  return <article ref={ref} className="c-card">{children}</article>;
});
