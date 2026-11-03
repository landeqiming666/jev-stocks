import type { ReactNode } from "react";

export interface DrawerProps {
  open: boolean;
  titleId: string;
  overlay: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ open, children }: DrawerProps) {
  return open ? <aside role="dialog">{children}</aside> : null;
}
