/** Small inline icon set (24px grid, stroke-based). Avoids an icon dependency. */
const paths = {
  phone: [
    'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z',
  ],
  shield: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'],
  shieldCheck: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'm9 12 2 2 4-4'],
  alert: [
    'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z',
    'M12 9v4',
    'M12 17h.01',
  ],
  check: ['M20 6 9 17l-5-5'],
  close: ['M18 6 6 18', 'M6 6l12 12'],
  chevronRight: ['m9 18 6-6-6-6'],
  chevronLeft: ['m15 18-6-6 6-6'],
  bell: ['M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9', 'M13.73 21a2 2 0 0 1-3.46 0'],
  clock: ['M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20', 'M12 6v6l4 2'],
  money: [
    'M4 6h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z',
    'M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 1 0 0-5',
    'M6 12h.01M18 12h.01',
  ],
  user: ['M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2', 'M12 3a4 4 0 1 0 0 8 4 4 0 1 0 0-8'],
  lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 0 1 8 0v4'],
  voice: ['M3 10v4', 'M7 6v12', 'M11 3v18', 'M15 8v8', 'M19 5v14', 'M23 10v4'],
  eyeOff: ['M9.9 4.24A9 9 0 0 1 12 4c7 0 10 8 10 8a13 13 0 0 1-1.67 2.68', 'M6.61 6.61A13.5 13.5 0 0 0 2 12s3 8 10 8a9.7 9.7 0 0 0 5.39-1.61', 'M14.12 14.12a3 3 0 1 1-4.24-4.24', 'M2 2l20 20'],
  refresh: ['M3 12a9 9 0 0 1 15-6.7L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-15 6.7L3 16', 'M3 21v-5h5'],
  callback: [
    'M15.05 5A5 5 0 0 1 19 8.95M15.05 1A9 9 0 0 1 23 8.94',
    'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z',
  ],
  message: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'],
  device: ['M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z', 'M11 18h2'],
  file: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6'],
  grid: ['M3 3h7v7H3z', 'M14 3h7v7h-7z', 'M14 14h7v7h-7z', 'M3 14h7v7H3z'],
  activity: ['M22 12h-4l-3 9L9 3l-3 9H2'],
  search: ['M11 3a8 8 0 1 0 0 16 8 8 0 1 0 0-16', 'm21 21-4.3-4.3'],
  download: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm7 10 5 5 5-5', 'M12 15V3'],
  upload: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm17 8-5-5-5 5', 'M12 3v12'],
  globe: ['M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20', 'M2 12h20', 'M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z'],
  puzzle: ['M19.4 13.5a2.5 2.5 0 1 0 0-3H18V7a1 1 0 0 0-1-1h-3.5V4.6a2.5 2.5 0 1 0-3 0V6H7a1 1 0 0 0-1 1v3.5h1.4a2.5 2.5 0 1 1 0 3H6V17a1 1 0 0 0 1 1h3.5v-1.4a2.5 2.5 0 1 1 3 0V18H17a1 1 0 0 0 1-1v-3.5z'],
  code: ['m16 18 6-6-6-6', 'm8 6-6 6 6 6'],
  dashboard: ['M3 3h8v10H3z', 'M13 3h8v6h-8z', 'M13 11h8v10h-8z', 'M3 15h8v6H3z'],
  list: ['M8 6h13', 'M8 12h13', 'M8 18h13', 'M3 6h.01', 'M3 12h.01', 'M3 18h.01'],
  chart: ['M3 3v18h18', 'M7 15l4-4 3 3 6-6'],
  bars: ['M3 21h18', 'M6 17V10', 'M11 17V5', 'M16 17v-7', 'M21 17v-3'],
  fileText: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6', 'M16 13H8', 'M16 17H8', 'M10 9H8'],
  play: ['M6 4l14 8-14 8z'],
  pause: ['M7 4h3v16H7z', 'M14 4h3v16h-3z'],
  arrowLeft: ['M19 12H5', 'm12 19-7-7 7-7'],
  arrowRight: ['M5 12h14', 'm12 5 7 7-7 7'],
  external: ['M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6', 'M15 3h6v6', 'M10 14 21 3'],
  users: ['M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2', 'M9 3a4 4 0 1 0 0 8 4 4 0 1 0 0-8', 'M23 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  fingerprint: ['M12 11v3a8 8 0 0 1-1.5 4.7', 'M8.5 8.5A5 5 0 0 1 17 12v1.5', 'M17 17.5c-.3 1.2-.8 2.3-1.5 3.3', 'M7 12a5 5 0 0 1 .5-2.2', 'M7 15.5c0 1.4-.4 2.7-1 3.8', 'M4.3 7.6A9 9 0 0 1 21 12v1', 'M3 12v.5'],
  filter: ['M22 3H2l8 9.46V19l4 2v-8.54z'],
  calendar: ['M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z', 'M16 2v4', 'M8 2v4', 'M3 10h18'],
  printer: ['M6 9V2h12v7', 'M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2', 'M6 14h12v8H6z'],
  send: ['m22 2-7 20-4-9-9-4z', 'M22 2 11 13'],
  userCheck: ['M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2', 'M8.5 3a4 4 0 1 0 0 8 4 4 0 1 0 0-8', 'm17 11 2 2 4-4'],
  link: ['M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71', 'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'],
} as const;

export type IconName = keyof typeof paths;

interface IconProps {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
  /** Provide a label only when the icon carries meaning on its own */
  label?: string;
}

export function Icon({ name, size = 18, strokeWidth = 1.9, className, label }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {paths[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
