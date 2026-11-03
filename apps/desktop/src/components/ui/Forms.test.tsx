import { createRef, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Button, Field, Input, Textarea, SearchInput, Radio, SegmentedControl } from "./index";

afterEach(cleanup);

it("button_variants_refs_disabled_reason_and_form_default", () => {
  const ref = createRef<HTMLButtonElement>(), click = vi.fn(), submit = vi.fn();
  const { rerender } = render(<form onSubmit={submit}><Button ref={ref} onClick={click}>Save</Button></form>);
  fireEvent.click(ref.current!);
  expect(click).toHaveBeenCalledTimes(1);
  expect(submit).not.toHaveBeenCalled();
  for (const variant of ["primary", "secondary", "text", "danger", "icon"] as const) {
    rerender(<Button ref={ref} variant={variant} disabled disabledReason="Blocked"
      aria-label="Save" onClick={click}>Save</Button>);
    expect(ref.current!.classList.contains(`c-button--${variant}`)).toBe(true);
    expect(ref.current!.title).toBe("Blocked");
    fireEvent.click(ref.current!);
  }
  expect(click).toHaveBeenCalledTimes(1);
  rerender(<Button ref={ref} loading onClick={click}>Save</Button>);
  expect(ref.current!.disabled).toBe(true);
  fireEvent.click(ref.current!);
  expect(click).toHaveBeenCalledTimes(1);
  expect(ref.current!.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
});

it("icon_button_without_name_is_rejected_in_development", () => {
  expect(() => render(<Button variant="icon" icon="x" />)).toThrow(/aria-label/);
});

it("field_unicode_count_defaultvalue_override_and_ref_survive_rerender", () => {
  const field = createRef<HTMLDivElement>(), input = createRef<HTMLTextAreaElement>();
  const { rerender } = render(<Field ref={field} id="note" label="Note" count={{ value: 99, max: 2 }}>
    <Textarea ref={input} value={"\u2003😀𠮷\u00a0"} readOnly />
  </Field>);
  expect(screen.getByText("2 / 2")).toBeTruthy();
  expect(screen.getByLabelText("Note")).toBe(input.current);
  expect(field.current!.className).toBe("c-field");
  rerender(<Field id="note" label="Note" count={{ value: 99, max: 2 }}>
    <Input defaultValue={"\ufeff😀𠮷x\u3000"} />
  </Field>);
  expect(screen.getByText("3 / 2").classList.contains("u-danger")).toBe(true);
  rerender(<Field id="note" label="Note" count={{ value: 7, max: 10 }}><Input type="number" value={3} readOnly /></Field>);
  expect(screen.getByText("7 / 10")).toBeTruthy();
});

it("field_descriptions_merge_stably_and_clear_stale_errors", () => {
  const child = <Input aria-describedby="external external" />;
  const { rerender } = render(<Field id="note" label="Note" error="Required" help="Help">{child}</Field>);
  const first = screen.getByRole("textbox").getAttribute("aria-describedby")!;
  expect(first.split(" ")).toHaveLength(3);
  rerender(<Field id="note" label="Note" error="Required" help="Help">{child}</Field>);
  expect(screen.getByRole("textbox").getAttribute("aria-describedby")).toBe(first);
  rerender(<Field id="note" label="Note" help="Help">{child}</Field>);
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("textbox").getAttribute("aria-invalid")).not.toBe("true");
  expect(screen.getByRole("textbox").getAttribute("aria-describedby")!.split(" ")).toHaveLength(2);
});

it("search_and_textarea_forward_control_props_and_combobox_links", () => {
  const input = createRef<HTMLInputElement>(), textarea = createRef<HTMLTextAreaElement>(), change = vi.fn();
  render(<><SearchInput ref={input} id="search" expanded value="ZZ" aria-label="Search"
    aria-controls="results" aria-activedescendant="option" onChange={change} invalid />
    <Textarea ref={textarea} aria-label="Note" invalid disabled />
  </>);
  expect(screen.getByRole("combobox")).toBe(input.current);
  expect(input.current!.getAttribute("aria-expanded")).toBe("true");
  expect(input.current!.getAttribute("aria-controls")).toBe("results");
  expect(input.current!.getAttribute("aria-activedescendant")).toBe("option");
  expect(input.current!.getAttribute("aria-invalid")).toBe("true");
  fireEvent.change(input.current!, { target: { value: "ZZAR" } });
  expect(change).toHaveBeenCalledOnce();
  expect(textarea.current!.rows).toBe(3);
  expect(textarea.current!.disabled).toBe(true);
});

it("radio_uses_native_control_and_hint_description", () => {
  const ref = createRef<HTMLInputElement>(), change = vi.fn();
  render(<Radio ref={ref} name="market" value="us" checked={false} label="Market" hint="Hint" onChange={change} />);
  const radio = screen.getByRole("radio", { name: "Market" });
  expect(radio).toBe(ref.current);
  expect(document.getElementById(radio.getAttribute("aria-describedby")!)!.textContent).toBe("Hint");
  fireEvent.click(radio);
  expect(change).toHaveBeenCalledWith("us");
});

it("segmented_is_controlled_roves_wraps_and_skips_disabled", () => {
  const change = vi.fn();
  const items = [{ value: "a", label: "A" }, { value: "b", label: "B", disabled: true }, { value: "c", label: "C" }];
  const { rerender } = render(<SegmentedControl name="window" label="Window" value="a" items={items} onChange={change} />);
  fireEvent.keyDown(screen.getByRole("radio", { name: "A" }), { key: "ArrowRight" });
  expect(change).toHaveBeenCalledWith("c");
  expect(screen.getByRole("radio", { name: "A" }).getAttribute("aria-checked")).toBe("true");
  expect(document.activeElement).toBe(screen.getByRole("radio", { name: "C" }));
  rerender(<SegmentedControl name="window" label="Window" value="c" items={items} onChange={change} />);
  for (const key of ["ArrowRight", "Home"]) {
    fireEvent.keyDown(screen.getByRole("radio", { name: "C" }), { key });
    expect(change).toHaveBeenLastCalledWith("a");
  }
  fireEvent.keyDown(screen.getByRole("radio", { name: "A" }), { key: "End" });
  expect(change).toHaveBeenLastCalledWith("c");
  expect(screen.getByRole("radio", { name: "B" }).tabIndex).toBe(-1);
});

it("segmented_disabled_selection_and_empty_group_keep_valid_tabstops", () => {
  const onChange = vi.fn();
  const { rerender } = render(<SegmentedControl name="window" label="Window" value="a"
    items={[{ value: "a", label: "A", disabled: true }, { value: "b", label: "B" }]} onChange={onChange} />);
  expect(screen.getByRole("radio", { name: "B" }).tabIndex).toBe(0);
  rerender(<SegmentedControl name="window" label="Window" value="a" items={[]} onChange={onChange} />);
  fireEvent.keyDown(screen.getByRole("radiogroup"), { key: "ArrowRight" });
  expect(onChange).not.toHaveBeenCalled();
});

it("controlled_inputs_update_from_user_changes", () => {
  function Controlled() {
    const [value, setValue] = useState("");
    return <Input value={value} aria-label="Input" onChange={event => setValue(event.target.value)} />;
  }
  render(<Controlled />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "ZZAR" } });
  expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("ZZAR");
});
