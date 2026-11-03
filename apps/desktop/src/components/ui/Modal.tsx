import type { ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
}

export function Modal({ open, children }: ModalProps) {
  return open ? <div role="dialog">{children}</div> : null;
}
