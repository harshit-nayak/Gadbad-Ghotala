/**
 * Where the detection backend (call-monitor/backend) lives.
 *
 * With no VITE_BACKEND_URL, this only guesses a same-host address when the
 * page itself is loaded over plain HTTP (local dev, LAN demo box) — there,
 * "same host, port 8000" is a reasonable default. On an HTTPS deployment
 * (Vercel, etc.) an unset VITE_BACKEND_URL means no backend is hosted yet,
 * so BACKEND_HTTP is left null: guessing `http://<page-host>:8000` would
 * build a `ws://` monitor URL that the browser blocks as mixed content on an
 * https page, and a plain `http://` fetch to it would equally be blocked.
 * Every caller (detectionFeed, AudioCheck, ...) already handles a missing
 * backend by falling back to the simulated demo.
 */
export const BACKEND_HTTP: string | null = import.meta.env.VITE_BACKEND_URL
  ? import.meta.env.VITE_BACKEND_URL.replace(/\/$/, '')
  : window.location.protocol === 'http:'
    ? `http://${window.location.hostname || 'localhost'}:8000`
    : null;

/**
 * Shared token for backends started with AUTH_TOKEN set (app/config.py). Sent
 * as `Authorization: Bearer` on REST calls and `?token=` on the monitor
 * WebSocket, since browsers can't set headers on a socket handshake.
 */
export const BACKEND_TOKEN: string | null = import.meta.env.VITE_BACKEND_TOKEN || null;

/**
 * The desktop capture client's local control API (client/control_server.py).
 * It runs on the same computer as the browser, not the web server, so this is
 * always localhost unless VITE_CLIENT_URL says otherwise.
 */
export const CLIENT_HTTP: string = (import.meta.env.VITE_CLIENT_URL || 'http://localhost:8001').replace(/\/$/, '');
