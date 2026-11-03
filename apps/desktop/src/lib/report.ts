import { errorCodeOf, requestIdOf } from "./errors";

export const DIAGNOSTIC_MAX = 4000;
const version = (value: string) => /^\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.-]+)?$/.test(value) && value.length <= 48 ? value : "unknown";
export function buildDiagnostic(input: { error: unknown; appVersion: string; protocolVersion: string }): string {
  return JSON.stringify({
    code: errorCodeOf(input.error) ?? "INTERNAL",
    requestId: requestIdOf(input.error),
    appVersion: version(input.appVersion),
    protocolVersion: version(input.protocolVersion),
    time: new Date().toISOString(),
  }, null, 2).slice(0, DIAGNOSTIC_MAX);
}
