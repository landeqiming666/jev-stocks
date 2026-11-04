import { forwardRef, type InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  numeric?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({
  invalid, numeric, className = "", ...props
}, ref) {
  return <input {...props} ref={ref} aria-invalid={invalid || props["aria-invalid"]}
    className={`c-input${numeric ? " c-input--num" : ""}${className ? ` ${className}` : ""}`} />;
});
