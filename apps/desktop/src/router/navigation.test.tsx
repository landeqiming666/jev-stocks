import { cleanup, act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RouterView } from "./RouterView";
import { useRoute, navigate } from "./useRoute";
import { parseHash, buildHash } from "./hash";

beforeEach(() => window.history.replaceState(null, "", "#/today"));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function Probe() { const { route, params } = useRoute(); return <output>{route}:{params.toString()}</output>; }
it("push_and_replace_update_route_without_hashchange_and_keep_query", () => {
  const push = vi.spyOn(window.history, "pushState"), replace = vi.spyOn(window.history, "replaceState");
  render(<Probe />);
  act(() => navigate("holdings", { state: "pending", extra: "a&b?中" }));
  expect(screen.getByRole("status").textContent).toContain("holdings:state=pending&extra=a%26b%3F%E4%B8%AD");
  expect(push).toHaveBeenCalledOnce();
  act(() => navigate("risk", { drawer: "one" }, { replace: true }));
  expect(replace).toHaveBeenCalledOnce();
  expect(screen.getByRole("status").textContent).toBe("risk:drawer=one");
});
it("popstate_and_native_hashchange_update_route", () => {
  render(<Probe />);
  act(() => { window.history.replaceState(null, "", "#/scan?unknown=yes"); window.dispatchEvent(new PopStateEvent("popstate")); });
  expect(screen.getByRole("status").textContent).toBe("scan:unknown=yes");
  act(() => { window.history.replaceState(null, "", "#/settings"); window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.getByRole("status").textContent).toBe("settings:");
});
it("unknown_empty_and_encoded_hashes_preserve_uninterpreted_parameters", () => {
  expect(parseHash("").route).toBe("today");
  expect(parseHash("#/missing?x=1&x=2").params.getAll("x")).toEqual(["1", "2"]);
  expect(parseHash(buildHash("today", { q: "a&b ?#" })).params.get("q")).toBe("a&b ?#");
});
it("page_switch_focuses_title_resets_scroll_and_renders_all_six_placeholders", async () => {
  render(<RouterView pageModules={{}} />);
  for (const route of ["today", "holdings", "trading", "risk", "scan", "settings"] as const) {
    const scroll = vi.fn();
    Object.defineProperty(document.querySelector("main"), "scrollTo", { value: scroll, configurable: true });
    act(() => navigate(route));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBe(document.activeElement));
    expect(document.title).toContain(screen.getByRole("heading", { level: 1 }).textContent);
    expect(screen.getByText("页面正在搭建。")).toBeTruthy();
    expect(scroll).toHaveBeenCalled();
  }
});

it("provided_business_page_replaces_the_placeholder_and_receives_route_focus", async () => {
  render(<RouterView pageModules={{ "../pages/today/index.tsx": { default: () => <main><h1>Today fixture</h1></main> } }} />);
  await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBe(document.activeElement));
  expect(screen.queryByText("页面正在搭建。")).toBeNull();
});
