import type { Evidence } from "../../rpc";
import { today } from "../../i18n/zh-CN/today";

export function EvidenceText({ evidence, titleOnly = false }: { evidence: Evidence; titleOnly?: boolean }) {
  const points = Array.from(evidence.passageText), start = evidence.sentenceStart, end = evidence.sentenceEnd;
  if (titleOnly || evidence.kind === "title") return <><p className="c-note">{today.titleOnly}</p><p className="c-passage">{evidence.text}</p></>;
  const valid = evidence.kind === "sentence" && start !== null && end !== null && Number.isInteger(start) && Number.isInteger(end) &&
    start >= 0 && end > start && end <= points.length && points.slice(start, end).join("") === evidence.text;
  return <>{!valid && <p className="c-note">{today.passageFallback}</p>}
    <p className="c-passage">{valid ? <>{points.slice(0, start).join("")}<mark className="c-evidence-mark">{points.slice(start, end).join("")}</mark>{points.slice(end).join("")}</> : evidence.passageText}</p></>;
}
