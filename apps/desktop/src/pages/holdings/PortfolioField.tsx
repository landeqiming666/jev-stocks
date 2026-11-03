import { cloneElement, useId, type ReactElement } from "react";
import type { FieldProps } from "../../components/ui";

// U-01 的 Field 从 value 按 JS trim 重算计数；本页需采用 Python strip 的码点数。
export function Field({ id, label, help, error, count, children }: FieldProps) {
  const suffix = useId(), helpId = `${suffix}-help`, errorId = `${suffix}-error`;
  return <div className={`c-field${error ? " has-error" : ""}`}>
    <label className="c-field__label" htmlFor={id}>{label}</label>
    {cloneElement(children as ReactElement<Record<string, unknown>>, {
      id, "aria-invalid": !!error,
      "aria-describedby": [help && helpId, error && errorId].filter(Boolean).join(" ") || undefined,
    })}
    {(help || count) && <div className="c-field__meta"><span id={helpId} className="c-field__help">{help}</span>
      {count && <span className={`c-field__count${count.value > count.max ? " u-danger" : ""}`}>{count.value} / {count.max}</span>}</div>}
    {error && <p id={errorId} role="alert" className="c-field__error">{error}</p>}
  </div>;
}
