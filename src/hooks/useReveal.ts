import { useEffect, useRef } from 'react';

/**
 * Adds `is-revealed` to the element once it scrolls into view.
 * Reduced-motion users get the revealed state immediately (the CSS transition
 * is disabled globally in base.css).
 */
export function useReveal<T extends HTMLElement>(options: { threshold?: number; once?: boolean } = {}) {
  const { threshold = 0.18, once = true } = options;
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      el.classList.add('is-revealed');
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            entry.target.classList.remove('is-revealed');
          }
        });
      },
      { threshold, rootMargin: '0px 0px -40px 0px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, once]);

  return ref;
}

/** Counts up to `value` when the element is revealed. Numbers only. */
export function useCountUp(value: number, active: boolean, durationMs = 900) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !active) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      el.textContent = String(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      el.textContent = String(Math.round(value * (1 - (1 - p) ** 3)));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, active, durationMs]);
  return ref;
}
