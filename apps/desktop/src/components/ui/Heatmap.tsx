export interface HeatmapProps {
  symbols: string[];
  matrix: (number | null)[][];
  label: string;
}

export function Heatmap({ label }: HeatmapProps) {
  return <svg role="img" aria-label={label}><rect /></svg>;
}
