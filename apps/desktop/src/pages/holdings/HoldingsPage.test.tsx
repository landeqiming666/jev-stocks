import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "../../app/store";
import { RpcError, type RpcClient } from "../../rpc";
import HoldingsPage from "./index";
import { ThesisEditor } from "./ThesisEditor";
import holdingFixture from "./__fixtures__/holdings.json";
import thesisFixture from "./__fixtures__/theses.json";
import searchFixture from "./__fixtures__/search-ze.json";
import type { Thesis } from "../../rpc/generated/types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => { resolve = r; });
  return { promise, resolve };
}
let holdings: typeof holdingFixture.items;
let theses: Thesis[];
const call = vi.fn(async (method: string, params: Record<string, unknown>): Promise<unknown> => {
  if (method === "holdings.list") return { ...holdingFixture, items: holdings };
  if (method === "thesis.list") return { items: theses.filter(t => !params.instrumentId || t.instrumentId === params.instrumentId) };
  if (method === "instruments.search") return searchFixture;
  if (method === "thesis.versions") return { items: [{ ...theses[0], version: 1, statement: "旧逻辑" }] };
  if (method === "prices.refresh") return { updated: 1, failed: [], asOf: "2026-10-30" };
  if (method === "holdings.archive") { holdings = holdings.filter(h => h.instrument.instrumentId !== params.instrumentId); return { ok: true }; }
  if (method === "thesis.archive") { theses = theses.filter(t => t.thesisId !== params.thesisId); return { ok: true }; }
  if (method === "thesis.update" || method === "thesis.create") return { ...theses[0], ...params, version: 3 };
  if (method === "holdings.upsert") return { ...holdings[0], ...params };
  throw new Error(method);
});
beforeEach(() => {
  holdings = structuredClone(holdingFixture.items);
  theses = structuredClone(thesisFixture.items) as Thesis[];
  call.mockClear();
  window.history.replaceState(null, "", "#/holdings");
  useAppStore.setState({ client: { call, subscribe: () => () => {} } as unknown as RpcClient });
});
afterEach(() => { cleanup(); useAppStore.getState().reset(); vi.useRealTimers(); });
async function expand() {
  const button = await screen.findByRole("button", { name: "展开 ZZAR" });
  fireEvent.keyDown(button.closest("tr")!, { key: "Enter" });
  await screen.findAllByText(theses[0]!.statement);
}
function edit() {
  return render(<ThesisEditor instrumentId="us:ZZAR" initial={theses[0]} onSaved={vi.fn()} onCancel={vi.fn()} />);
}

describe("holdings real page consumer", () => {
  it("renders six rows, statuses and watch-only quantity", async () => {
    render(<HoldingsPage />);
    expect((await screen.findAllByRole("row")).length).toBe(7);
    expect(screen.getAllByText("守护中").length).toBe(2);
    expect(screen.getAllByText("有待处理").length).toBe(2);
    expect(screen.getAllByText("没有逻辑").length).toBe(2);
    expect(screen.getByText("关注")).toBeTruthy();
  });
  it("starts with six 44px skeleton rows and no fake empty list", async () => {
    const pending = deferred<typeof holdingFixture>();
    call.mockImplementationOnce(() => pending.promise);
    render(<HoldingsPage />);
    expect(screen.getAllByTestId("holding-skeleton").length).toBe(6);
    await act(async () => pending.resolve(holdingFixture));
  });
  it("empty list hides header and offers focusable search", async () => {
    holdings = [];
    render(<HoldingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "去添加" }));
    expect(document.activeElement).toBe(screen.getByRole("combobox"));
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("row toggles with Enter and Space and holds aria-expanded", async () => {
    render(<HoldingsPage />); await expand();
    const row = screen.getByRole("button", { name: "收起 ZZAR" }).closest("tr")!;
    expect(row.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(row, { key: " " });
    expect(row.getAttribute("aria-expanded")).toBe("false");
  });
  it("thesis route opens correct row without opening editor", async () => {
    window.history.replaceState(null, "", "#/holdings?thesis=" + theses[0]!.thesisId);
    render(<HoldingsPage />);
    await screen.findByRole("button", { name: "收起 ZZAR" });
    expect(screen.queryByRole("textbox", { name: "逻辑" })).toBeNull();
  });
  it("production hash state never replaces service data", async () => {
    holdings = [];
    window.history.replaceState(null, "", "#/holdings?state=expanded");
    render(<HoldingsPage />);
    await screen.findByText("先添加第一只标的");
    expect(screen.queryByText("ZZAR")).toBeNull();
  });
  it("five active theses disable creation", async () => {
    theses = Array.from({ length: 5 }, (_, n) => ({ ...theses[0]!, thesisId: "id-" + n }));
    render(<HoldingsPage />); await expand();
    expect((screen.getByRole("button", { name: "添加逻辑" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("每只标的最多 5 条有效逻辑")).toBeTruthy();
  });
  it("holding archive waits for modal confirmation", async () => {
    render(<HoldingsPage />); await expand();
    fireEvent.click(screen.getByRole("button", { name: "归档持仓" }));
    expect(call.mock.calls.some(([m]) => m === "holdings.archive")).toBe(false);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认归档" }));
    await waitFor(() => expect(call).toHaveBeenCalledWith("holdings.archive", { instrumentId: "us:ZZAR" }));
    await waitFor(() => expect(screen.queryByText("ZZAR")).toBeNull());
  });
  it("archive failure retains item and modal and reports error", async () => {
    render(<HoldingsPage />); await expand();
    fireEvent.click(screen.getByRole("button", { name: "归档持仓" }));
    call.mockRejectedValueOnce(new RpcError("INTERNAL", "synthetic"));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认归档" }));
    await screen.findByText("归档失败，请重试");
    expect(screen.getByText("ZZAR")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
  it("partial refresh lists each failure and keeps cached dates", async () => {
    render(<HoldingsPage />); await screen.findByText("ZZAR");
    call.mockResolvedValueOnce({ updated: 1, asOf: "2026-11-02", failed: [{ instrumentId: "us:ZZFD", error: { code: "SOURCE_UNAVAILABLE", message: "synthetic" } }] });
    fireEvent.click(screen.getByRole("button", { name: "刷新行情" }));
    await screen.findByText(/ZZFD.*行情刷新失败/);
    expect(screen.getByText(/已更新 1 个标的/)).toBeTruthy();
    expect(screen.getAllByText(/10月30日/).length).toBeGreaterThan(0);
  });
  it("version history displays immutable old content", async () => {
    render(<HoldingsPage />); await expand();
    fireEvent.click(screen.getAllByRole("button", { name: "版本历史" })[0]!);
    await screen.findByText("旧逻辑");
    expect(call.mock.calls.some(([m]) => m === "thesis.versions")).toBe(true);
  });
  it("thesis archive waits for confirmation and preserves other thesis", async () => {
    render(<HoldingsPage />); await expand();
    const first = theses[0]!.thesisId, remaining = theses[1]!.statement;
    fireEvent.click(screen.getAllByRole("button", { name: "归档" })[0]!);
    expect(call.mock.calls.some(([m]) => m === "thesis.archive")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "确认归档" }));
    await waitFor(() => expect(call).toHaveBeenCalledWith("thesis.archive", { thesisId: first }));
    await screen.findByText(remaining);
  });
  it("unmount aborts holdings request without rendering a stale response", async () => {
    const pending = deferred<typeof holdingFixture>();
    call.mockImplementationOnce(() => pending.promise);
    const view = render(<HoldingsPage />);
    const signal = (call.mock.calls[0] as unknown as [string, object, { signal: AbortSignal }])[2].signal;
    view.unmount(); expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve(holdingFixture));
    expect(screen.queryByText("ZZAR")).toBeNull();
  });
});

describe("thesis editing boundaries", () => {
  it("whitespace counts zero and rejects empty save", async () => {
    edit(); fireEvent.change(screen.getByLabelText("逻辑"), { target: { value: "   " } });
    expect(screen.getByText("0 / 500")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await screen.findByText("逻辑内容不能为空");
    expect(call).not.toHaveBeenCalled();
  });
  it("501 codepoints overflow immediately", () => {
    edit(); fireEvent.change(screen.getByLabelText("逻辑"), { target: { value: "中".repeat(501) } });
    expect(screen.getByText("501 / 500")).toBeTruthy();
    expect(screen.getByLabelText("逻辑").getAttribute("aria-invalid")).toBe("true");
  });
  it("Ctrl+Enter sends trimmed statement with expectedVersion", async () => {
    edit(); const field = screen.getByLabelText("逻辑");
    fireEvent.change(field, { target: { value: " new thesis " } });
    fireEvent.keyDown(field, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(call).toHaveBeenCalledWith("thesis.update", expect.objectContaining({ statement: "new thesis", expectedVersion: 2 })));
  });
  it("conflict preserves draft; refreshing latest does not silently overwrite", async () => {
    edit(); fireEvent.change(screen.getByLabelText("逻辑"), { target: { value: "my draft" } });
    call.mockRejectedValueOnce(new RpcError("CONFLICT", "synthetic", false, { currentVersion: 3 }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await screen.findByText("这条逻辑已被修改，请刷新后再试");
    theses[0] = { ...theses[0]!, version: 3, statement: "remote content" };
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await screen.findByText("remote content");
    expect((screen.getByLabelText("逻辑") as HTMLTextAreaElement).value).toBe("my draft");
    fireEvent.click(screen.getByRole("button", { name: /以第 3 版为基础/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(call).toHaveBeenLastCalledWith("thesis.update", expect.objectContaining({ expectedVersion: 3, statement: "my draft" })));
  });
  it("Escape asks before discarding and keeps input on cancel", async () => {
    edit(); fireEvent.change(screen.getByLabelText("逻辑"), { target: { value: "draft" } });
    fireEvent.keyDown(screen.getByLabelText("逻辑"), { key: "Escape" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "继续编辑" }));
    expect((screen.getByLabelText("逻辑") as HTMLTextAreaElement).value).toBe("draft");
  });
  it("pending save disables fields and suppresses repeated shortcuts", async () => {
    edit(); const pending = deferred<unknown>(); call.mockImplementationOnce(() => pending.promise);
    const field = screen.getByLabelText("逻辑");
    fireEvent.keyDown(field, { key: "Enter", metaKey: true });
    fireEvent.keyDown(field, { key: "Enter", ctrlKey: true });
    expect(call.mock.calls.filter(([m]) => m === "thesis.update")).toHaveLength(1);
    expect((field as HTMLTextAreaElement).disabled).toBe(true);
    await act(async () => pending.resolve(theses[0]));
  });
});

describe("instrument search races", () => {
  it("debounces 300ms and drops old response during the next debounce", async () => {
    vi.useFakeTimers(); render(<HoldingsPage />);
    await act(async () => {});
    const old = deferred<typeof searchFixture>();
    call.mockImplementationOnce(() => old.promise);
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "z" } });
    await act(async () => vi.advanceTimersByTimeAsync(299));
    expect(call.mock.calls.filter(([m]) => m === "instruments.search").length).toBe(0);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    fireEvent.change(input, { target: { value: "qq" } });
    await act(async () => old.resolve(searchFixture));
    expect(screen.queryByRole("option")).toBeNull();
    call.mockResolvedValueOnce({ items: [] });
    await act(async () => vi.advanceTimersByTimeAsync(300));
    expect(screen.getByText("没有找到匹配的美股标的")).toBeTruthy();
  });
  it("rejects negative quantity before upsert and marks duplicates", async () => {
    render(<HoldingsPage />); await screen.findByText("ZZAR");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ze" } });
    const option = await screen.findByRole("option", { name: /ZZNW/ });
    expect(screen.getAllByText("已添加").length).toBe(3);
    fireEvent.click(option);
    fireEvent.change(screen.getByLabelText("数量"), { target: { value: "-5" } });
    fireEvent.click(screen.getByRole("button", { name: "保存持仓" }));
    await screen.findByText("数量必须是非负数字");
    expect(call.mock.calls.some(([m]) => m === "holdings.upsert")).toBe(false);
  });
  it("missing instrument catalog explains the email requirement", async () => {
    render(<HoldingsPage />); await screen.findByText("ZZAR");
    call.mockRejectedValueOnce(new RpcError("CONFIG_REQUIRED", "synthetic"));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ze" } });
    await screen.findByText("填写联系邮箱后才能下载标的表");
  });
  it("search cleanup aborts a pending call", async () => {
    render(<HoldingsPage />); await screen.findByText("ZZAR");
    const pending = deferred<unknown>(); call.mockImplementationOnce(() => pending.promise);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ze" } });
    await waitFor(() => expect(call.mock.calls.some(([m]) => m === "instruments.search")).toBe(true));
    const signal = (call.mock.calls.find(([m]) => m === "instruments.search") as unknown as [string, object, { signal: AbortSignal }])[2].signal;
    cleanup(); expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve(searchFixture));
  });
});
