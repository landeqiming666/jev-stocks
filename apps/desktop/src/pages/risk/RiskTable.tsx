import type { RiskResult } from "../../rpc";
import { risk } from "../../i18n/zh-CN/risk";
import { cellTitle, number } from "./format";

export function RiskTable({ result }: { result: RiskResult }) {
  const { symbols, matrix } = result.correlation;
  return <div className="p-risk__table"><div className="c-table-wrap" tabIndex={0} aria-label={risk.tableLabel}>
    <table className="c-table"><caption className="u-visually-hidden">{risk.tableLabel}</caption>
      <thead><tr><th scope="col">{risk.instrument}</th>{symbols.map((symbol, i) =>
        <th scope="col" className="c-table__num" key={i}>{symbol}</th>)}</tr></thead>
      <tbody>{matrix.map((row, i) => <tr key={i}><th scope="row">{symbols[i]}</th>
        {row.map((value, j) => <td key={j} className="c-table__num"
          title={cellTitle(symbols[i]!, symbols[j]!, value, true)}
          aria-label={cellTitle(symbols[i]!, symbols[j]!, value, true)}>{number(value)}</td>)}
      </tr>)}</tbody>
    </table></div>{matrix.some(row => row.includes(null)) && <p className="c-note">{risk.nullNote}</p>}</div>;
}
