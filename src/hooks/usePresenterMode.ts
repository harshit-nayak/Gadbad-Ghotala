import { useEffect } from 'react';

/**
 * Presenter mode reveals demo controls (restart, skip, flow stepper, answer
 * prompts) that are hidden in the normal product UI. Elements opt in with the
 * `presenter-only` class; visibility is pure CSS on <html data-presenter>.
 *
 * Toggle with Shift + P (ignored while typing in a field), or start with
 * `?presenter` in the URL.
 */
const startsOn =
  typeof window !== 'undefined' && /[?&]presenter\b/.test(`${window.location.search}${window.location.hash}`);

export function usePresenterMode(onToggle?: (on: boolean) => void) {
  useEffect(() => {
    const root = document.documentElement;
    if (startsOn) root.dataset.presenter = 'on';

    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
      if (event.code !== 'KeyP' || !event.shiftKey || event.metaKey || event.ctrlKey || event.altKey) return;
      const on = root.dataset.presenter !== 'on';
      if (on) root.dataset.presenter = 'on';
      else delete root.dataset.presenter;
      onToggle?.(on);
    };

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onToggle]);
}
