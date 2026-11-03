import type { RefObject } from "react";
import type { IconName } from "./types";

export interface MenuProps {
  items: { id: string; label: string; icon?: IconName; danger?: boolean; disabled?: boolean }[];
  onSelect: (id: string) => void;
  onClose: () => void;
  triggerRef: RefObject<HTMLButtonElement | null>;
}

export function Menu({ items }: MenuProps) {
  return <div role="menu">{items.map(item =>
    <button key={item.id} role="menuitem">{item.label}</button>,
  )}</div>;
}
