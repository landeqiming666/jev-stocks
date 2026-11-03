import { forwardRef } from "react";
import { Icon } from "./Icon";
import { Input, type InputProps } from "./Input";

export type SearchInputProps = InputProps & { expanded?: boolean };

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(function SearchInput({
  expanded = false, ...props
}, ref) {
  return <div className="c-search"><Icon name="search" />
    <Input {...props} ref={ref} type="search" role="combobox" aria-expanded={expanded}
      aria-autocomplete={props["aria-autocomplete"] ?? "list"}
      aria-controls={props["aria-controls"] ?? (expanded && props.id ? `${props.id}-list` : undefined)} />
  </div>;
});
