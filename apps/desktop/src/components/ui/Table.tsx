import { forwardRef, type ReactNode } from "react";

export interface TableProps { children: ReactNode; label: string; }
export const ROW_H = "44px";
export const HEAD_H = "36px";
export const Table = forwardRef<HTMLTableElement, TableProps>(function Table({ children, label }, ref) {
  return <div className="c-table-wrap"><table ref={ref} className="c-table" aria-label={label}>{children}</table></div>;
});
