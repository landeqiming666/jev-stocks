import { Button, SegmentedControl } from "../../components/ui";
import type { RiskResult } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";

export const WINDOWS = ["6M", "1Y", "3Y"] as const;
export function RiskControls({ window, table, onWindow, onTable }: {
  window: RiskResult["window"]["label"]; table: boolean;
  onWindow: (window: RiskResult["window"]["label"]) => void; onTable: (value: boolean) => void;
}) {
  return <div className="p-risk__controls"><div className="u-grow">
    <SegmentedControl name="window" label={risk.window} value={window}
      items={WINDOWS.map(value => ({ value, label: value }))}
      onChange={value => onWindow(value as RiskResult["window"]["label"])} />
    <SegmentedControl name="currency" label={risk.currency} value="USD" onChange={() => {}}
      items={[{ value: "USD", label: risk.usd }, { value: "CNY", label: risk.cny, disabled: true, title: risk.cnyV1 }]} />
    <span className="c-note">{risk.cnyNote}</span>
  </div><Button variant={table ? "primary" : "secondary"} aria-pressed={table} onClick={() => onTable(!table)}>
    {risk.table}
  </Button></div>;
}
