import { createRef, StrictMode } from "react";
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { common } from "../../i18n/zh-CN/common";
import { Banner, Toast, Skeleton, EmptyState, Card, Table, Probability, MarketBadge, EngineBadge, StatusTag, Progress, Heatmap, BarList, VerdictChip } from "./index";

afterEach(() => { cleanup(); vi.useRealTimers(); });

it("toast_success_timer_uses_latest_callback_error_persists_and_unmount_clears_timer", () => {
  vi.useFakeTimers();
  const first = vi.fn(), second = vi.fn();
  const { rerender, unmount } = render(<StrictMode><Toast tone="success" text="Saved" onClose={first} /></StrictMode>);
  vi.advanceTimersByTime(2000);
  rerender(<StrictMode><Toast tone="success" text="Saved" onClose={second} /></StrictMode>);
  vi.advanceTimersByTime(2000);
  expect(first).not.toHaveBeenCalled();
  expect(second).toHaveBeenCalledOnce();
  rerender(<Toast tone="error" text="Failed" onClose={first} />);
  vi.advanceTimersByTime(10000);
  expect(first).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: common.dismiss }));
  expect(first).toHaveBeenCalledOnce();
  rerender(<Toast tone="success" text="Saved again" onClose={second} />);
  unmount(); vi.advanceTimersByTime(4000);
  expect(second).toHaveBeenCalledOnce();
});

it("presentation_components_forward_original_roots_without_tab_stops", () => {
  const card = createRef<HTMLElement>(), table = createRef<HTMLTableElement>(), skeleton = createRef<HTMLDivElement>();
  const empty = createRef<HTMLDivElement>(), banner = createRef<HTMLDivElement>(), toast = createRef<HTMLDivElement>();
  const probability = createRef<HTMLSpanElement>(), market = createRef<HTMLSpanElement>(), engine = createRef<HTMLSpanElement>();
  const tag = createRef<HTMLSpanElement>(), progress = createRef<HTMLDivElement>(), heatmap = createRef<SVGSVGElement>();
  const barlist = createRef<HTMLUListElement>(), verdict = createRef<HTMLSpanElement>();
  render(<><Card ref={card}>Card</Card><Table ref={table} label="Table"><tbody><tr><td>Row</td></tr></tbody></Table>
    <Skeleton ref={skeleton} rows={2} /><EmptyState ref={empty} title="Empty" text="Help" action={<button>Action</button>} />
    <Banner ref={banner} tone="danger" text="Danger" /><Toast ref={toast} tone="error" text="Error" onClose={vi.fn()} />
    <Probability ref={probability} value={0.9} /><MarketBadge ref={market} market="cn" />
    <EngineBadge ref={engine} active="jev_direct" state="degraded" modelId="jev-1.14.0" />
    <StatusTag ref={tag} tone="ok">OK</StatusTag><Progress ref={progress} value={1} max={2} label="Progress" />
    <Heatmap ref={heatmap} symbols={["ZZAR"]} matrix={[[1]]} label="Heatmap" />
    <BarList ref={barlist} label="Variance" items={[]} /><VerdictChip ref={verdict} kind="none" /></>);
  for (const ref of [card, table, skeleton, empty, banner, toast, probability, market, engine, tag, progress, heatmap, barlist, verdict]) {
    expect(ref.current).not.toBeNull();
    expect(ref.current!.hasAttribute("tabindex")).toBe(false);
  }
  expect(card.current!.tagName).toBe("ARTICLE");
  expect(table.current!.tagName).toBe("TABLE");
  expect(table.current!.parentElement!.className).toBe("c-table-wrap");
  expect(probability.current!.childElementCount).toBe(0);
  expect(market.current!.textContent).toBe(common.market.cn);
  expect(engine.current!.title).toBe(common.engineDegradedTitle);
  expect(engine.current!.querySelector("svg")).not.toBeNull();
  expect(banner.current!.getAttribute("role")).toBe("alert");
  expect(toast.current!.getAttribute("role")).toBe("alert");
  expect(skeleton.current!.children).toHaveLength(2);
});

it("all_verdicts_and_engine_unconfigured_use_central_copy", () => {
  const { rerender } = render(<VerdictChip kind="support" />);
  for (const kind of ["support", "none", "overturn", "weaken", "uncertain"] as const) {
    rerender(<VerdictChip kind={kind} />);
    expect(screen.getByText(common.verdict[kind]).querySelector("svg")).not.toBeNull();
  }
  rerender(<EngineBadge active={null} state="unconfigured" modelId="" />);
  expect(screen.getByText(common.engine.unconfigured)).toBeTruthy();
});

it("component_css_scopes_shell_overlap_and_preserves_tokens_and_motion_rules", () => {
  const css = readFileSync("src/components/ui/components.css", "utf8");
  expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b|outline\s*:\s*none/);
  for (const line of css.split("\n")) {
    if (!line.includes("{")) continue;
    for (const match of line.split("{")[0]!.matchAll(/\.c-(?:icon(?:--20)?|engine|tag(?:--\w+)?)(?![\w-])/g)) {
      expect(line.slice(match.index! + match[0].length)).toMatch(/^\[data-ui\]/);
    }
  }
  expect(css).toContain("min-height: 32px");
  expect(css).toContain("top: var(--top-h)");
  expect(css).toContain("bottom: var(--status-h)");
  expect(css).toContain(".l-scrim.c-modal-scrim");
});
