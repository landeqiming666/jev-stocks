import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import ready from "../app/__fixtures__/bootstrap.json";
import type { Bootstrap } from "../rpc";

afterEach(cleanup);
it("shell_renders_disclaimer_and_engine_badge", async () => {
  const { AppShell } = await import("./AppShell");
  const { useAppStore } = await import("../app/store");
  useAppStore.setState({ bootstrap: { status: "ready", value: ready as Bootstrap, error: null } });
  render(<AppShell><h1>Page</h1></AppShell>);
  expect(screen.getByText(/Jev 直连 · jev-1\.14\.0/)).toBeTruthy();
  expect(screen.getByText("仅记录与提醒，不构成投资建议。")).toBeTruthy();
});
