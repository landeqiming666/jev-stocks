import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Icon } from "./Icon";
import type { ButtonVariant, IconName } from "./types";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: IconName;
  disabledReason?: string;
}

export const BUTTON_H = 32;
export const ICON_SIZE = 16;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  children, variant = "secondary", loading = false, icon, disabled, disabledReason,
  type = "button", className = "", title, ...props
}, ref) {
  if (import.meta.env.DEV && variant === "icon" && !props["aria-label"]?.trim()) {
    throw new Error("Icon buttons require aria-label");
  }
  return <button {...props} ref={ref} type={type} disabled={disabled || loading}
    title={disabled && disabledReason ? disabledReason : title}
    aria-busy={loading || props["aria-busy"]}
    className={`c-button c-button--${variant}${loading ? " is-loading" : ""}${className ? ` ${className}` : ""}`}>
    {loading ? <Icon name="refresh-cw" /> : icon ? <Icon name={icon} /> : null}{children}
  </button>;
});
