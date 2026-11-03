import { forwardRef, type ReactNode } from "react";

export interface EmptyStateProps { title: string; text?: string; action?: ReactNode; display?: boolean; }
export const EmptyState = forwardRef<HTMLDivElement, EmptyStateProps>(function EmptyState({
  title, text, action, display,
}, ref) {
  const Heading = display ? "h1" : "h2";
  return <div ref={ref} className={`c-empty${display ? " c-empty--display" : ""}`}>
    <div className="c-empty__art" aria-hidden="true" />
    <Heading className="c-empty__title">{title}</Heading>
    {text && <p className="c-empty__text">{text}</p>}{action}
  </div>;
});
