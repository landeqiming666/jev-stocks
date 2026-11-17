import { useEffect, useRef, useState } from "react";

export function useDraft(saved: string) {
  const [value, setValue] = useState(saved);
  const current = useRef(saved), dirty = useRef(false);
  useEffect(() => {
    if (!dirty.current) { current.current = saved; setValue(saved); }
  }, [saved]);
  return { value, edit(next: string) { dirty.current = true; current.current = next; setValue(next); },
    accept(submitted: string, normalized = submitted) {
      // 写入期间仍允许编辑；成功回包只确认当时提交的草稿。
      if (current.current === submitted) { dirty.current = false; current.current = normalized; setValue(normalized); }
    } };
}
