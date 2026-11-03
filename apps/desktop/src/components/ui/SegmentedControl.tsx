export interface SegmentedControlProps {
  name: string;
  label: string;
  value: string;
  items: { value: string; label: string; disabled?: boolean; title?: string }[];
  onChange: (value: string) => void;
}

export function SegmentedControl({ items, value }: SegmentedControlProps) {
  return <div role="radiogroup">{items.map(item =>
    <button key={item.value} role="radio" aria-checked={item.value === value}>
      {item.label}
    </button>,
  )}</div>;
}
