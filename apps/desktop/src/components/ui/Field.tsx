import { Children, cloneElement, forwardRef, isValidElement, useId, type ReactNode } from "react";

export interface FieldProps {
  id: string;
  label: string;
  help?: string;
  error?: string;
  count?: { value: number; max: number };
  children: ReactNode;
}

type ControlProps = {
  id?: string; value?: unknown; defaultValue?: unknown;
  "aria-describedby"?: string; "aria-invalid"?: boolean | "true" | "false" | "grammar" | "spelling";
};

export const Field = forwardRef<HTMLDivElement, FieldProps>(function Field({
  id, label, help, error, count, children,
}, ref) {
  const suffix = useId();
  const helpId = `${suffix}-help`, errorId = `${suffix}-err`;
  const nodes = Children.toArray(children);
  const child = nodes.length === 1 && isValidElement<ControlProps>(nodes[0]) ? nodes[0] : null;
  const text = child?.props.value ?? child?.props.defaultValue;
  const length = typeof text === "string" ? Array.from(text.trim()).length : count?.value;
  const describedby = [...new Set([
    ...(child?.props["aria-describedby"]?.split(/\s+/).filter(Boolean) ?? []),
    ...(help ? [helpId] : []), ...(error ? [errorId] : []),
  ])].join(" ");
  return <div ref={ref} className={`c-field${error ? " has-error" : ""}`}>
    <label className="c-field__label" htmlFor={id}>{label}</label>
    {child ? cloneElement(child, { id, "aria-describedby": describedby || undefined,
      "aria-invalid": error ? true : child.props["aria-invalid"] }) : children}
    {(help || count) && <div className="c-field__meta">
      <span id={help ? helpId : undefined} className={help ? "c-field__help" : undefined}>{help}</span>
      {count && <span className={`c-field__count${length! > count.max ? " u-danger" : ""}`}>
        {length} / {count.max}
      </span>}
    </div>}
    {error && <p className="c-field__error" id={errorId} role="alert">{error}</p>}
  </div>;
});
