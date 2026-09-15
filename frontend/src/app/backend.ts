/**
 * Where the detection backend (call-monitor/backend) lives.
 * Defaults to port 8000 on the host serving this page; override with
 * VITE_BACKEND_URL, e.g. VITE_BACKEND_URL=http://192.168.1.20:8000.
 */
export const BACKEND_HTTP: string = (
  import.meta.env.VITE_BACKEND_URL || `http://${window.location.hostname || 'localhost'}:8000`
).replace(/\/$/, '');

/**
 * The desktop capture client's local control API (client/control_server.py).
 * It runs on the same computer as the browser, not the web server, so this is
 * always localhost unless VITE_CLIENT_URL says otherwise.
 */
export const CLIENT_HTTP: string = (import.meta.env.VITE_CLIENT_URL || 'http://localhost:8001').replace(/\/$/, '');
