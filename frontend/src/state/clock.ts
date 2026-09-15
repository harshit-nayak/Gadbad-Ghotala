import { DEMO_NOW } from '../domain/format';

const sessionStart = Date.now();

/** Demo-world "now": DEMO_NOW plus real time elapsed since the page loaded. */
export const demoNowIso = () =>
  new Date(new Date(DEMO_NOW).getTime() + (Date.now() - sessionStart)).toISOString();

let counter = 0;
export const uid = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(counter++).toString(36)}`;
