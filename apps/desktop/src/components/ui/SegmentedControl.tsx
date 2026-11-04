import { forwardRef, type KeyboardEvent } from "react";

export interface SegmentedControlProps {
  name: string;
  label: string;
  value: string;
  items: { value: string; label: string; disabled?: boolean; title?: string }[];
  onChange: (value: string) => void;
}

export const SegmentedControl = forwardRef<HTMLDivElement, SegmentedControlProps>(function SegmentedControl({
  name, label, items, value, onChange,
}, ref) {
  const enabled = items.filter(item => !item.disabled);
  const tabValue = enabled.find(item => item.value === value)?.value ?? enabled[0]?.value;
  function move(event: KeyboardEvent<HTMLButtonElement>, current: string) {
    const keys = ["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key) || event.nativeEvent.isComposing || !enabled.length) return;
    event.preventDefault();
    const index = enabled.findIndex(item => item.value === current);
    const next = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 :
      (index + (event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length;
    const item = enabled[next]!;
    const buttons = event.currentTarget.parentElement!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
    buttons[next]?.focus();
    onChange(item.value);
  }
  return <div ref={ref} className="c-segmented" role="radiogroup" aria-label={label}>
    {items.map(item => <button key={item.value} type="button" name={name} value={item.value}
      className={`c-segmented__item${item.value === value ? " is-active" : ""}`}
      role="radio" aria-checked={item.value === value} disabled={item.disabled} title={item.title}
      tabIndex={!item.disabled && item.value === tabValue ? 0 : -1}
      onClick={() => onChange(item.value)} onKeyDown={event => move(event, item.value)}>{item.label}</button>)}
  </div>;
});
