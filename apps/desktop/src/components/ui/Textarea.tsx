import { forwardRef, type TextareaHTMLAttributes } from "react";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean };

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea({
  invalid, className = "", rows = 3, ...props
}, ref) {
  return <textarea {...props} ref={ref} rows={rows} aria-invalid={invalid || props["aria-invalid"]}
    className={`c-textarea${className ? ` ${className}` : ""}`} />;
});
