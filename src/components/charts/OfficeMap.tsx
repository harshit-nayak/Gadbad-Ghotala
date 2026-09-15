import { useMemo, useState } from 'react';
import type { Office } from '../../domain/types';
import './charts.css';

/** Approximate office coordinates (lat, lon). */
const officeCoords: Record<Office, [number, number]> = {
  'Delhi NCR': [28.6, 77.2],
  Mumbai: [19.08, 72.88],
  Pune: [18.52, 73.86],
  Bengaluru: [12.97, 77.59],
  Chennai: [13.08, 80.27],
  Hyderabad: [17.39, 78.49],
  Kolkata: [22.57, 88.36],
};

/** Coarse outline of India (lat, lon) used only to clip the dot matrix. */
const outline: [number, number][] = [
  [35.6, 74.3], [35.0, 77.8], [32.5, 79.3], [30.2, 81.0], [28.4, 83.0], [27.3, 84.4], [26.6, 88.0], [27.8, 88.8],
  [26.8, 89.9], [27.5, 92.0], [28.2, 95.3], [27.2, 96.9], [24.5, 94.6], [22.8, 93.2], [23.9, 91.6], [25.1, 89.9],
  [22.6, 88.9], [21.6, 88.2], [20.3, 86.7], [18.3, 84.0], [16.5, 82.2], [15.5, 80.2], [13.1, 80.3], [10.3, 79.9],
  [8.1, 77.5], [10.0, 76.2], [12.9, 74.8], [15.5, 73.8], [18.9, 72.8], [20.9, 72.8], [22.2, 68.9], [23.6, 68.3],
  [24.6, 71.1], [27.8, 70.3], [30.1, 73.9], [32.5, 74.6],
];

/** Label side per office so neighbouring pins don't collide. */
const labelSide: Record<Office, 'left' | 'right'> = {
  'Delhi NCR': 'right',
  Mumbai: 'left',
  Pune: 'left',
  Bengaluru: 'left',
  Chennai: 'right',
  Hyderabad: 'right',
  Kolkata: 'left',
};

const W = 300;
const H = 330;
const project = ([lat, lon]: [number, number]) => [((lon - 67.5) / 30) * W, ((37 - lat) / 30.5) * H] as const;

function inside(px: number, py: number, poly: (readonly [number, number])[]) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export function OfficeMap({ counts, label }: { counts: { key: Office; count: number }[]; label: string }) {
  const [active, setActive] = useState<Office | null>(null);
  const dots = useMemo(() => {
    const poly = outline.map(project);
    const list: [number, number][] = [];
    for (let y = 3; y < H; y += 7) for (let x = 3; x < W; x += 7) if (inside(x, y, poly)) list.push([x, y]);
    return list;
  }, []);
  const max = Math.max(1, ...counts.map((c) => c.count));
  const byOffice = new Map(counts.map((c) => [c.key, c.count]));
  const offices = (Object.keys(officeCoords) as Office[]).sort((a, b) => (byOffice.get(b) ?? 0) - (byOffice.get(a) ?? 0));

  return (
    <div className="office-map">
      <svg viewBox={`-34 6 ${W + 60} ${H - 14}`} role="img" aria-label={label} className="office-map__svg">
        {dots.map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r={1.5} className="office-map__dot" />
        ))}
        {offices.map((office) => {
          const [x, y] = project(officeCoords[office]);
          const count = byOffice.get(office) ?? 0;
          const r = count ? 5 + Math.sqrt(count / max) * 15 : 3.5;
          const side = labelSide[office];
          const labelX = side === 'right' ? x + Math.max(r, 6) + 4 : x - Math.max(r, 6) - 4;
          const labelY = office === 'Pune' ? y + 11 : office === 'Mumbai' ? y - 7 : y;
          return (
            <g key={office} className={`office-map__pin ${active && active !== office ? 'is-dim' : ''}`} onMouseEnter={() => setActive(office)} onMouseLeave={() => setActive(null)}>
              {count > 0 && <circle cx={x} cy={y} r={r} className="office-map__halo" />}
              <circle cx={x} cy={y} r={3.2} className={`office-map__core ${count ? '' : 'is-empty'}`} />
              <text x={labelX} y={labelY} dy="0.32em" textAnchor={side === 'right' ? 'start' : 'end'} className="office-map__label">
                {office} <tspan className="office-map__count">{count}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
