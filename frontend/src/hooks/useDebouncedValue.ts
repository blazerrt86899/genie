"use client";

import { useEffect, useState } from "react";

/** Returns `value` after it has stayed unchanged for `ms`. */
export function useDebouncedValue<T>(value: T, ms = 180): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
