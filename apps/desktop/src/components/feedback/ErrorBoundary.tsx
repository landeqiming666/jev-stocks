import { Component, type ReactNode } from "react";
import { useAppStore } from "../../app/store";
import { feedback } from "../../i18n/zh-CN/feedback";
import { createErrorId, errorCodeOf, requestIdOf } from "../../lib/errors";
import { buildDiagnostic } from "../../lib/report";
import { pushToast } from "../../lib/toast-store";
import { Button, Card } from "../ui";
import "./feedback.css";

interface BoundaryState { errorId: string | null; diagnostic: string; copyFailed: boolean; }
const initial: BoundaryState = { errorId: null, diagnostic: "", copyFailed: false };
export class ErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, BoundaryState> {
  state = initial;
  private mounted = false;
  private copyRevision = 0;
  static getDerivedStateFromError(error: unknown): BoundaryState {
    const errorId = createErrorId();
    const bootstrap = useAppStore.getState().bootstrap.value;
    const safeError = { code: errorCodeOf(error) ?? "INTERNAL", data: { requestId: requestIdOf(error) ?? errorId } };
    return { errorId, copyFailed: false, diagnostic: buildDiagnostic({
      error: safeError, appVersion: bootstrap?.appVersion ?? "unknown", protocolVersion: bootstrap?.protocolVersion ?? "unknown",
    }) };
  }
  componentDidMount() { this.mounted = true; }
  componentWillUnmount() { this.mounted = false; this.copyRevision++; }
  private retry = () => { this.copyRevision++; this.setState(initial); };
  private copy = async () => {
    const revision = ++this.copyRevision;
    try {
      await navigator.clipboard.writeText(this.state.diagnostic);
      if (this.mounted && revision === this.copyRevision) {
        this.setState({ copyFailed: false });
        pushToast({ tone: "success", text: feedback.copied });
      }
    } catch {
      if (this.mounted && revision === this.copyRevision) this.setState({ copyFailed: true });
    }
  };
  render() {
    if (!this.state.errorId) return this.props.children;
    if (this.props.fallback !== undefined) return this.props.fallback;
    return <div className="c-feedback-error"><Card>
      <h2 className="u-h2">{feedback.renderError}</h2>
      <p className="u-mono c-feedback-error-id">{feedback.errorId(this.state.errorId)}</p>
      <div className="u-row"><Button onClick={this.retry}>{feedback.retry}</Button>
        <Button onClick={() => { void this.copy(); }}>{feedback.copy}</Button></div>
      {this.state.copyFailed && <p role="alert">{feedback.copyFailed}</p>}
    </Card></div>;
  }
}
