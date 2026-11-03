import { forwardRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusLayer, useRootRef } from "./focus-layer";

export interface DrawerProps {
  open: boolean;
  titleId: string;
  overlay: boolean;
  onClose: () => void;
  children: ReactNode;
}

export const Drawer = forwardRef<HTMLDivElement, DrawerProps>(function Drawer({
  open, titleId, overlay, onClose, children,
}, ref) {
  const [root, setRef] = useRootRef(ref);
  const isTop = useFocusLayer(root, { open, trap: overlay, rank: 1, titleId, onClose });
  if (import.meta.env.DEV && open && !titleId.trim()) throw new Error("Drawer requires titleId");
  if (!open) return null;
  const dialog = <div ref={setRef} className={`c-drawer${overlay ? " c-drawer--overlay" : ""}`}
    role="dialog" aria-modal={overlay} aria-labelledby={titleId} tabIndex={-1}>{children}</div>;
  return overlay ? createPortal(<>
    <div className="l-scrim c-drawer-scrim" aria-hidden="true" onClick={() => { if (isTop()) onClose(); }} />
    {dialog}
  </>, document.body) : dialog;
});
