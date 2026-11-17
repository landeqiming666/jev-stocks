import { Fragment } from "react";
import { Progress } from "../../components/ui/Progress";
import { StatusTag } from "../../components/ui/StatusTag";
import { scan } from "../../i18n/zh-CN/scan";
import type { ScanRun } from "../../rpc";
import type { ScanProgress } from "./useScanRuns";
import { cost, duration, engine, number, time, tone } from "./format";

export function RunTable({ items, selected, progress, onOpen }: {
  items: ScanRun[]; selected: string | null; progress: Record<string, ScanProgress>; onOpen: (runId: string) => void;
}) {
  return <div className="c-card c-card--flush"><div className="c-table-wrap">
    <table className="c-table p-scan__table" aria-label={scan.title}>
      <thead><tr>{scan.columns.map((label, index) => <th key={label} scope="col" className={index >= 2 && index <= 9 ? "c-table__num" : undefined}>{label}</th>)}</tr></thead>
      <tbody>{items.map(run => <Fragment key={run.runId}>
        <tr className={`c-table__click${selected === run.runId ? " is-selected" : ""}`} tabIndex={0}
          data-run-id={run.runId} aria-expanded={selected === run.runId} aria-controls={selected === run.runId ? "scan-detail-title" : undefined}
          onClick={event => { event.currentTarget.focus(); onOpen(run.runId); }} onKeyDown={event => {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(run.runId); }
          }}>
          <td>{time(run.startedAt)}</td><td><StatusTag tone={tone[run.status]}>{scan.statuses[run.status]}</StatusTag></td>
          {[run.stats.instruments, run.stats.filings, run.stats.passages, run.stats.decisions, run.stats.requests, run.stats.inputTokens].map((value, index) => <td key={index} className="c-table__num">{number(value)}</td>)}
          <td className="c-table__num">{cost(run.stats.estCostUsd)}</td><td className="c-table__num">{duration(run.stats.durationMs)}</td><td>{engine(run.engine)}</td>
        </tr>
        {progress[run.runId] && ["queued", "running"].includes(run.status) && <tr className="p-scan__progress-row"><td colSpan={11}>
          <Progress value={progress[run.runId]!.done} max={progress[run.runId]!.total} label={progress[run.runId]!.message} />
        </td></tr>}
      </Fragment>)}</tbody>
    </table>
  </div></div>;
}
