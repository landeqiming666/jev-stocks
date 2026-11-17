import { StrictMode, useState } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useAppStore } from "../../app/store";
import type { DecisionDetail, Evidence } from "../../rpc";
import { EvidenceDrawer, safeEvidenceUrl } from "./EvidenceDrawer";
import { EvidenceText } from "./EvidenceText";
import { deferred, example, overturnDetail, readyBoot, testClient } from "../../pages/today/test-support";

beforeEach(() => useAppStore.getState().reset());
afterEach(() => { cleanup(); useAppStore.getState().reset(); });
function mount(detail = overturnDetail(), overlay = true) {
  const fake = testClient(undefined, detail), onClose = vi.fn(), onAct = vi.fn(async () => {});
  useAppStore.setState({ client: fake.client, bootstrap: { status: "ready", value: readyBoot(), error: null } });
  function Harness() {
    const [id, setId] = useState<string | null>(null);
    return <><button onClick={() => setId(detail.decisionId)}>Open evidence</button>
      <EvidenceDrawer decisionId={id} overlay={overlay} onClose={() => { onClose(); setId(null); }}
        onAct={onAct} onReopen={async () => {}} /></>;
  }
  render(<StrictMode><Harness /></StrictMode>);
  const trigger = screen.getByRole("button", { name: "Open evidence" });
  trigger.focus(); fireEvent.click(trigger);
  return { ...fake, trigger, onClose, onAct };
}
test("drawer_esc_closes_and_restores_focus", async () => {
  const { trigger, onClose } = mount();
  await screen.findByText(overturnDetail().thesisStatement);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(trigger);
});
test("drawer_renders_five_probability_bars", async () => {
  mount(example<DecisionDetail>("decision.get", "weaken"));
  const list = await screen.findByRole("list", { name: "五个问题的概率" });
  expect(list.querySelectorAll("li")).toHaveLength(5);
  expect(list.textContent).toContain("未设置失效条件");
});
test("drawer_sentence_highlights_offsets", () => {
  const evidence: Evidence = { kind: "sentence", passageText: "0123456789abcdef", text: "456789ab",
    sentenceStart: 4, sentenceEnd: 12, filePart: "主文档" };
  const { container } = render(<EvidenceText evidence={evidence} />);
  expect(container.querySelectorAll("mark.c-evidence-mark")).toHaveLength(1);
  expect(container.querySelector("mark")?.textContent).toBe("456789ab");
});
test("drawer_processed_shows_reopen_only", async () => {
  mount(example<DecisionDetail>("decision.get", "processed"));
  await screen.findByRole("button", { name: "重新打开" });
  expect(screen.queryByRole("button", { name: "仍然成立" })).toBeNull();
});
test("drawer_code_point_offsets_and_invalid_bounds_fallback", () => {
  const evidence: Evidence = { kind: "sentence", passageText: "前😀文😀后", text: "😀文😀",
    sentenceStart: 1, sentenceEnd: 4, filePart: "主文档" };
  const view = render(<EvidenceText evidence={evidence} />);
  expect(view.container.querySelector("mark")?.textContent).toBe("😀文😀");
  view.rerender(<EvidenceText evidence={{ ...evidence, sentenceEnd: 6 }} />);
  expect(view.container.querySelector("mark")).toBeNull();
  expect(screen.getByText("未能定位到单句，以下为整段原文")).toBeTruthy();
});
test("drawer_async_old_request_cannot_overwrite_new_decision", async () => {
  const fake = testClient(), old = deferred<DecisionDetail>(), latest = example<DecisionDetail>("decision.get", "weaken");
  fake.call.mockImplementationOnce(() => old.promise);
  useAppStore.setState({ client: fake.client });
  const props = { overlay: false, onClose: vi.fn(), onAct: async () => {}, onReopen: async () => {} };
  const view = render(<EvidenceDrawer {...props} decisionId="old" />);
  fake.call.mockResolvedValueOnce(latest);
  view.rerender(<EvidenceDrawer {...props} decisionId={latest.decisionId} />);
  await screen.findByText(latest.thesisStatement);
  old.resolve(overturnDetail());
  await waitFor(() => expect(screen.queryByText(overturnDetail().thesisStatement)).toBeNull());
});
test("drawer_unmount_aborts_and_does_not_call_owned_client_dispose", async () => {
  const fake = testClient(), pending = deferred<DecisionDetail>();
  fake.call.mockImplementation(() => pending.promise);
  useAppStore.setState({ client: fake.client });
  const view = render(<EvidenceDrawer decisionId="id" overlay={false} onClose={() => {}}
    onAct={async () => {}} onReopen={async () => {}} />);
  const options = (fake.call.mock.calls[0] as unknown as [string, object, { signal: AbortSignal }])[2];
  view.unmount();
  expect(options.signal.aborted).toBe(true);
  expect(fake.client.dispose).not.toHaveBeenCalled();
  pending.resolve(overturnDetail());
});
test("drawer_trimmed_unicode_note_and_duplicate_submission", async () => {
  const fake = mount();
  const field = await screen.findByRole("textbox", { name: "备注（可选）" });
  fireEvent.change(field, { target: { value: `  ${"😀".repeat(201)}  ` } });
  const action = screen.getByRole("button", { name: "仍然成立" }) as HTMLButtonElement;
  expect(action.disabled).toBe(true);
  fireEvent.change(field, { target: { value: `  ${"😀".repeat(200)}  ` } });
  fireEvent.click(action); fireEvent.click(action);
  await waitFor(() => expect(fake.onAct).toHaveBeenCalledOnce());
  expect(fake.onAct).toHaveBeenCalledWith("still_valid", "😀".repeat(200));
});
test("drawer_https_sec_domain_only_blocks_credentials_ports_and_confusable_hosts", () => {
  expect(safeEvidenceUrl("https://www.sec.gov/Archives/document.htm")).toBe(true);
  for (const url of ["http://www.sec.gov/a", "https://sec.gov/a", "https://www.sec.gov.evil.test/a",
    "https://user@www.sec.gov/a", "https://www.sec.gov:8443/a", "javascript:alert(1)"]) expect(safeEvidenceUrl(url)).toBe(false);
});
test("drawer_title_only_uses_title_and_invalid_text_mismatch_falls_back", () => {
  const detail = example<DecisionDetail>("decision.get", "title_only");
  const view = render(<EvidenceText evidence={detail.evidence} />);
  expect(screen.getByText("仅依据标题判定")).toBeTruthy();
  expect(view.container.querySelector("mark")).toBeNull();
  view.rerender(<EvidenceText evidence={{ ...overturnDetail().evidence, text: "does not match offsets" }} />);
  expect(screen.getByText("未能定位到单句，以下为整段原文")).toBeTruthy();
  expect(view.container.querySelector("mark")).toBeNull();
});
