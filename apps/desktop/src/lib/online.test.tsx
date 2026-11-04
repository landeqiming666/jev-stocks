import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";
import { useOnline } from "./online";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function Probe() { return <p>{useOnline() ? "online" : "offline"}</p>; }
test("strictmode_online_subscribers_share_events_and_remove_them_after_unmount", () => {
  const add = vi.spyOn(window, "addEventListener"), remove = vi.spyOn(window, "removeEventListener");
  const view = render(<StrictMode><Probe /><Probe /></StrictMode>);
  fireEvent(window, new Event("offline"));
  expect(screen.getAllByText("offline")).toHaveLength(2);
  view.unmount();
  for (const event of ["online", "offline"]) {
    expect(remove.mock.calls.filter(call => call[0] === event).length).toBe(add.mock.calls.filter(call => call[0] === event).length);
  }
});
test("server_render_defaults_to_online", () => { expect(renderToString(<Probe />)).toContain("online"); });
