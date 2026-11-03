export type VerdictKind = "overturn" | "weaken" | "support" | "none" | "uncertain";

export function VerdictChip({ kind }: { kind: VerdictKind }) {
  return <span>{kind}</span>;
}
