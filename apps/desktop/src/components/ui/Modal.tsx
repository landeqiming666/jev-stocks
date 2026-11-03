import { forwardRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusLayer, useRootRef } from "./focus-layer";

export interface ModalProps {
  open: boolean;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
}

export const Modal = forwardRef<HTMLDivElement, ModalProps>(function Modal({ open, titleId, onClose, children }, ref) {
  const [root, setRef] = useRootRef(ref);
  const isTop = useFocusLayer(root, { open, trap: true, rank: 2, titleId, modal: true, onClose });
  if (!open) return null;
  return createPortal(<>
    <div className="l-scrim c-modal-scrim" aria-hidden="true" onClick={() => { if (isTop()) onClose(); }} />
    <div ref={setRef} className="c-modal" role="dialog" aria-modal="true" aria-labelledby={titleId}
      tabIndex={-1}>{children}</div>
  </>, document.body);
});
