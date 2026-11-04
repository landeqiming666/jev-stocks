import { useCallback, useLayoutEffect, useRef, type ForwardedRef, type RefObject } from "react";
import { common } from "../../i18n/zh-CN/common";

interface Layer { node: HTMLElement; rank: number; initial: () => HTMLElement; origin: HTMLElement | null; }
const layers: Layer[] = [];
const top = () => layers.reduce<Layer | undefined>((best, layer) =>
  !best || layer.rank >= best.rank ? layer : best, undefined);

export function focusable(node: HTMLElement): HTMLElement[] {
  return [...node.querySelectorAll<HTMLElement>(
    'button, input, textarea, select, a[href], [tabindex], [contenteditable="true"]',
  )].filter(element => {
    if ((element.tabIndex < 0 && element.getAttribute("role") !== "menuitem") || element.matches(':disabled, input[type="hidden"]')) return false;
    for (let current: HTMLElement | null = element; current; current = current.parentElement) {
      const style = window.getComputedStyle(current);
      if (current.hidden || current.inert || style.display === "none" || style.visibility === "hidden") return false;
    }
    return true;
  });
}

export function useRootRef<T extends HTMLElement>(ref: ForwardedRef<T>) {
  const root = useRef<T | null>(null);
  const setRef = useCallback((node: T | null) => {
    root.current = node;
    if (typeof ref === "function") ref(node);
    else if (ref) ref.current = node;
  }, [ref]);
  return [root, setRef] as const;
}

export function useFocusLayer(root: RefObject<HTMLElement | null>, {
  open, trap, rank, titleId, modal = false, onClose, restoreRef,
}: {
  open: boolean; trap: boolean; rank: number; titleId?: string; modal?: boolean;
  onClose: () => void; restoreRef?: RefObject<HTMLButtonElement | null>;
}) {
  const callback = useRef(onClose);
  const origin = useRef<HTMLElement | null>(null);
  const session = useRef(false);
  useLayoutEffect(() => { callback.current = onClose; }, [onClose]);
  useLayoutEffect(() => {
    if (!open) { session.current = false; origin.current = null; return; }
    const candidate = root.current;
    if (!candidate) return;
    const node: HTMLElement = candidate;
    const restoreTarget = restoreRef?.current;
    const layerRank = rank === 3 ? node.closest(".c-modal") ? 2.5 : 1.5 : rank;
    // StrictMode 的清理会重新 setup；同一次打开必须保留最初的触发元素。
    if (!session.current) {
      const active = node.ownerDocument.activeElement;
      const previous = top();
      // 嵌套子浮层可能先执行 layout effect，不能把子浮层控件当作父抽屉的触发点。
      origin.current = restoreTarget ?? (previous && previous.rank > layerRank && previous.node.contains(active) ? previous.origin :
        active instanceof HTMLElement && active !== document.body ? active : null);
      session.current = true;
    }
    const heading = titleId ? [...node.querySelectorAll<HTMLElement>("[id]")].find(item => item.id === titleId) : undefined;
    const hadTabIndex = heading?.getAttribute("tabindex");
    if (heading && hadTabIndex === null) heading.tabIndex = -1;
    function initial() {
      const inputs = focusable(node);
      if (modal) return inputs.find(item => item.matches("input, textarea, select")) ??
        inputs.find(item => item.tagName === "BUTTON" && item.textContent?.trim() === common.cancel) ?? inputs[0] ?? node;
      return heading ?? inputs[0] ?? node;
    }
    const layer: Layer = { node, rank: layerRank, initial, origin: origin.current };
    layers.push(layer);
    if (top() === layer) initial().focus();
    function keydown(event: KeyboardEvent) {
      if (top() !== layer || event.defaultPrevented || event.isComposing) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        callback.current();
        if (restoreTarget?.isConnected) restoreTarget.focus();
      } else if (event.key === "Tab" && trap) {
        const targets = focusable(node), first = targets[0], last = targets.at(-1);
        const active = node.ownerDocument.activeElement;
        if (!first || !last) { event.preventDefault(); node.focus(); }
        else if (event.shiftKey && (active === first || !targets.includes(active as HTMLElement))) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && (active === last || !node.contains(active))) {
          event.preventDefault(); first.focus();
        }
      }
    }
    function focusin(event: FocusEvent) {
      if (trap && top() === layer && !node.contains(event.target as Node)) initial().focus();
    }
    node.ownerDocument.addEventListener("keydown", keydown, true);
    node.ownerDocument.addEventListener("focusin", focusin, true);
    return () => {
      node.ownerDocument.removeEventListener("keydown", keydown, true);
      node.ownerDocument.removeEventListener("focusin", focusin, true);
      const wasTop = top() === layer;
      layers.splice(layers.indexOf(layer), 1);
      for (const pending of layers) {
        if (pending.origin && node.contains(pending.origin)) pending.origin = layer.origin;
      }
      if (heading && hadTabIndex === null) heading.removeAttribute("tabindex");
      if (wasTop) {
        const current = top(), destination = restoreTarget?.isConnected ? restoreTarget : layer.origin;
        if (current && (!destination?.isConnected || !current.node.contains(destination))) current.initial().focus();
        else if (destination?.isConnected) destination.focus();
      }
    };
  }, [open, trap, rank, titleId, modal, root, restoreRef]);
  return () => top()?.node === root.current;
}
