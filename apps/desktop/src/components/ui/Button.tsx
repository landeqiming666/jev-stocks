import type { ButtonHTMLAttributes } from "react";
import type { ButtonVariant, IconName } from "./types";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: IconName;
  disabledReason?: string;
}

// CR 裁定前的 TDD 空实现，仅用于执行规定的失败断言。
export function Button({ children }: ButtonProps) {
  return <button>{children}</button>;
}
