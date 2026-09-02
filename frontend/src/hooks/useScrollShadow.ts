"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Tracks whether a scroll container is pinned to its top / bottom edge, so a
 * sticky header (or footer) can drop a shadow only while content is hidden
 * behind it. rAF-throttled; also re-checks on resize and content growth.
 */
export function useScrollShadow<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const raf = useRef<number | null>(null);
  const [atTop, setAtTop] = useState(true);
  const [atBottom, setAtBottom] = useState(true);

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    setAtTop(scrollTop <= 0);
    setAtBottom(scrollHeight - clientHeight - scrollTop <= 1);
  }, []);

  const onScroll = useCallback(() => {
    if (raf.current != null) return;
    raf.current = requestAnimationFrame(() => {
      raf.current = null;
      measure();
    });
  }, [measure]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (raf.current != null) cancelAnimationFrame(raf.current);
    };
  }, [measure]);

  return { ref, onScroll, atTop, atBottom };
}
