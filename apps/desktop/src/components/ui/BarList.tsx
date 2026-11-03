export interface BarListProps {
  items: { label: string; value: number }[];
  label: string;
}

export function BarList({ items, label }: BarListProps) {
  return <ul aria-label={label}>{items.map(item =>
    <li key={item.label}>{item.label}: {String(item.value * 100)}%</li>,
  )}</ul>;
}
