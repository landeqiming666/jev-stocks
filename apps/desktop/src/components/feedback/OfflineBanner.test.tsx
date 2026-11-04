import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { useAppStore } from "../../app/store";
import bootstrap from "../../app/__fixtures__/bootstrap.json";
import type { Bootstrap } from "../../rpc";
import { dismissToast, getToasts } from "../../lib/toast-store";
import { OfflineBanner } from "./OfflineBanner";

afterEach(() => { cleanup(); useAppStore.getState().reset(); getToasts().forEach(item => dismissToast(item.id)); });
test("offline_banner_reacts_to_window_event", () => {
  render(<OfflineBanner />);
  fireEvent(window, new Event("offline"));
  expect(screen.getByText(/当前离线/)).toBeTruthy();
});

test("bootstrap_offline_keeps_banner_until_both_sources_recover", () => {
  useAppStore.setState({ bootstrap: { status: "ready", value: { ...bootstrap, offline: true } as Bootstrap, error: null } });
  render(<OfflineBanner />);
  fireEvent(window, new Event("offline")); fireEvent(window, new Event("online"));
  expect(screen.getByText(/当前离线/)).toBeTruthy();
  expect(getToasts()).toHaveLength(0);
  act(() => useAppStore.setState({ bootstrap: { status: "ready", value: { ...bootstrap, offline: false } as Bootstrap, error: null } }));
  expect(screen.queryByText(/当前离线/)).toBeNull();
  expect(getToasts().map(item => item.text)).toEqual(["已恢复联网"]);
});
