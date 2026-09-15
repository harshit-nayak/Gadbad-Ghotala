/**
 * The app uses hash routing, so a plain `href="#section"` would be read as a
 * route. Landing links keep the href for semantics but scroll manually.
 */
export function scrollToId(event: { preventDefault: () => void }, href: string) {
  event.preventDefault();
  const id = href.replace(/^#/, '');
  const target = document.getElementById(id);
  if (!target) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
}
