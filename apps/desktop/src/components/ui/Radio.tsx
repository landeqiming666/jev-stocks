import { forwardRef, useId } from "react";

export type RadioProps = {
  name: string; value: string; checked: boolean; label: string; hint?: string;
  onChange: (value: string) => void;
};

export const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio({
  name, value, checked, label, hint, onChange,
}, ref) {
  const hintId = useId();
  return <label className={`c-radio${checked ? " is-checked" : ""}`}>
    <input ref={ref} type="radio" name={name} value={value} checked={checked} aria-label={label}
      aria-describedby={hint ? hintId : undefined} onChange={() => onChange(value)} />
    <span><span className="c-radio__title">{label}</span>
      {hint && <><br /><span className="c-radio__hint" id={hintId}>{hint}</span></>}
    </span>
  </label>;
});
