import { forwardRef, type RefObject, type KeyboardEvent } from "react";
import type { IconName } from "./types";
import { Icon } from "./Icon";
import { focusable, useFocusLayer, useRootRef } from "./focus-layer";

export interface MenuProps {
  items: { id: string; label: string; icon?: IconName; danger?: boolean; disabled?: boolean }[];
  onSelect: (id: string) => void;
  onClose: () => void;
  triggerRef: RefObject<HTMLButtonElement | null>;
}

export const Menu = forwardRef<HTMLDivElement, MenuProps>(function Menu({ items, onSelect, onClose, triggerRef }, ref) {
  const [root, setRef] = useRootRef(ref);
  const close = () => { onClose(); triggerRef.current?.focus(); };
  useFocusLayer(root, { open: true, trap: false, rank: 3, onClose: close, restoreRef: triggerRef });
  function move(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Tab") { close(); return; }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || event.nativeEvent.isComposing) return;
    event.preventDefault();
    const enabled = focusable(event.currentTarget);
    if (!enabled.length) return;
    const index = enabled.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 :
      (index + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length;
    enabled[next]?.focus();
  }
  return <div ref={setRef} className="c-menu" role="menu" aria-labelledby={triggerRef.current?.id}
    tabIndex={-1} onKeyDown={move}>
    {items.map(item => <button key={item.id} type="button" role="menuitem" disabled={item.disabled}
      className={`c-menu__item${item.danger ? " u-danger" : ""}`} tabIndex={-1}
      onClick={() => { onSelect(item.id); close(); }}>{item.icon && <Icon name={item.icon} />}{item.label}</button>)}
  </div>;
});
