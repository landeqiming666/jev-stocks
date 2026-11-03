import type { ReactNode } from "react";

export interface FieldProps {
  id: string;
  label: string;
  help?: string;
  error?: string;
  count?: { value: number; max: number };
  children: ReactNode;
}

export function Field({ children }: FieldProps) {
  return <div>{children}</div>;
}
