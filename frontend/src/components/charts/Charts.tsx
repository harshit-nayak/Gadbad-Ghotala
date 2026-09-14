/**
 * Lightweight SVG charts. Colours come from CSS variables (--chart-*, --risk,
 * --warn...) so every chart follows the area theme. No chart dependency.
 */
import { useId, useState, type CSSProperties, type ReactNode } from 'react';
import { useElementWidth } from '../../hooks/useElementWidth';
import './charts.css';

export interface SeriesDef<K extends string> {
  key: K;
  label: string;
  color: string;
}

export interface ChartDatum<K extends string> {
  label: string;
  /** Longer label for the tooltip */
  detail?: string;
  values: Record<K, number>;
}

const niceMax = (value: number) => {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude >= value) ?? 10;
  return step * magnitude;
};

const compact = (n: number) => (n >= 1000 ? `${+(n / 1000).toFixed(1)}k` : String(n));

function Legend<K extends string>({ series }: { series: SeriesDef<K>[] }) {
  return (
    <ul className="legend">
      {series.map((s) => (
        <li key={s.key}>
          <span className="legend__swatch" style={{ background: s.color }} />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

function Tooltip<K extends string>({ datum, series, x, width }: { datum: ChartDatum<K>; series: SeriesDef<K>[]; x: number; width: number }) {
  const left = Math.min(Math.max(x, 70), width - 70);
  return (
    <div className="chart-tip" style={{ left }} role="presentation">
      <p className="chart-tip__title">{datum.detail ?? datum.label}</p>
      {series.map((s) => (
        <p key={s.key} className="chart-tip__row">
          <span className="legend__swatch" style={{ background: s.color }} />
          {s.label}
          <strong className="tabular">{datum.values[s.key].toLocaleString('en-IN')}</strong>
        </p>
      ))}
    </div>
  );
}

interface AxisChartProps<K extends string> {
  data: ChartDatum<K>[];
  series: SeriesDef<K>[];
  height?: number;
  label: string;
  /** Show every nth x label */
  labelEvery?: number;
}

const PAD = { top: 12, right: 8, bottom: 26, left: 34 };

function useAxis<K extends string>(data: ChartDatum<K>[], keys: K[], width: number, height: number, stacked: boolean) {
  const max = niceMax(
    Math.max(...data.map((d) => (stacked ? keys.reduce((sum, k) => sum + d.values[k], 0) : Math.max(...keys.map((k) => d.values[k])))), 0),
  );
  const innerW = Math.max(10, width - PAD.left - PAD.right);
  const innerH = height - PAD.top - PAD.bottom;
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const ticks = [0, max / 2, max];
  return { max, innerW, innerH, y, ticks };
}

function Grid({ ticks, y, width }: { ticks: number[]; y: (v: number) => number; width: number }) {
  return (
    <g className="chart-grid">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
          <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
            {compact(Math.round(t))}
          </text>
        </g>
      ))}
    </g>
  );
}

/** Vertical stacked bars over time. */
export function StackedBars<K extends string>({ data, series, height = 220, label, labelEvery = 1 }: AxisChartProps<K>) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const keys = series.map((s) => s.key);
  const { innerW, y, ticks } = useAxis(data, keys, width, height, true);
  const slot = innerW / Math.max(1, data.length);
  const barW = Math.max(3, Math.min(26, slot * 0.62));

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="img" aria-label={label}>
        <Grid ticks={ticks} y={y} width={width} />
        {data.map((d, i) => {
          let acc = 0;
          const x = PAD.left + i * slot + (slot - barW) / 2;
          return (
            <g key={d.label + i} className={hover === null || hover === i ? '' : 'chart-dim'}>
              {series.map((s) => {
                const v = d.values[s.key];
                const top = y(acc + v);
                const h = y(acc) - top;
                acc += v;
                return h > 0 ? <rect key={s.key} x={x} y={top} width={barW} height={Math.max(0, h - 1)} rx={Math.min(3, barW / 3)} fill={s.color} /> : null;
              })}
              {i % labelEvery === 0 && (
                <text className="chart-x" x={x + barW / 2} y={height - 8} textAnchor="middle">
                  {d.label}
                </text>
              )}
              <rect
                className="chart-hit"
                x={PAD.left + i * slot}
                y={PAD.top}
                width={slot}
                height={height - PAD.top - PAD.bottom}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          );
        })}
      </svg>
      {hover !== null && <Tooltip datum={data[hover]} series={series} x={PAD.left + hover * slot + slot / 2} width={width} />}
      <Legend series={series} />
    </div>
  );
}

/** Lines over time; the first series is drawn with a soft area fill. */
export function LineChart<K extends string>({ data, series, height = 220, label, labelEvery = 1 }: AxisChartProps<K>) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const gradientId = useId();
  const keys = series.map((s) => s.key);
  const { innerW, y, ticks } = useAxis(data, keys, width, height, false);
  const step = innerW / Math.max(1, data.length - 1);
  const x = (i: number) => PAD.left + i * step;
  const base = y(0);

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="img" aria-label={label}>
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={series[0].color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={series[0].color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <Grid ticks={ticks} y={y} width={width} />
        {series.map((s, si) => {
          const points = data.map((d, i) => `${x(i)},${y(d.values[s.key])}`);
          return (
            <g key={s.key}>
              {si === 0 && <path d={`M${x(0)},${base} L${points.join(' L')} L${x(data.length - 1)},${base} Z`} fill={`url(#${gradientId})`} />}
              <path d={`M${points.join(' L')}`} fill="none" stroke={s.color} strokeWidth={si === 0 ? 2.2 : 1.8} strokeDasharray={si === 0 ? undefined : '4 4'} strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}
        {data.map((d, i) =>
          i % labelEvery === 0 ? (
            <text key={d.label + i} className="chart-x" x={x(i)} y={height - 8} textAnchor="middle">
              {d.label}
            </text>
          ) : null,
        )}
        {hover !== null && (
          <g>
            <line className="chart-cursor" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={base} />
            {series.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(data[hover].values[s.key])} r={4} fill="var(--surface)" stroke={s.color} strokeWidth={2} />
            ))}
          </g>
        )}
        {data.map((d, i) => (
          <rect key={`hit-${d.label}-${i}`} className="chart-hit" x={x(i) - step / 2} y={PAD.top} width={step} height={base - PAD.top} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
        ))}
      </svg>
      {hover !== null && <Tooltip datum={data[hover]} series={series} x={x(hover)} width={width} />}
      <Legend series={series} />
    </div>
  );
}

export interface BarListItem {
  key: string;
  label: ReactNode;
  value: number;
  /** Optional right-side text instead of the raw value */
  display?: string;
  color?: string;
}

export function BarList({ items, total, emptyText = 'No data' }: { items: BarListItem[]; total?: number; emptyText?: string }) {
  if (items.length === 0) return <p className="subtle">{emptyText}</p>;
  const max = Math.max(...items.map((i) => i.value));
  const sum = total ?? items.reduce((s, i) => s + i.value, 0);
  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li key={item.key} className="bar-list__row">
          <span className="bar-list__label">{item.label}</span>
          <span className="bar-list__value tabular">
            {item.display ?? item.value}
            <span className="bar-list__share">{sum ? Math.round((item.value / sum) * 100) : 0}%</span>
          </span>
          <span className="bar-list__track" aria-hidden="true">
            <span style={{ width: `${(item.value / max) * 100}%`, background: item.color ?? 'var(--chart-1)' }} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export interface Slice {
  key: string;
  label: string;
  value: number;
  color: string;
}

export function Donut({ slices, size = 150, centre, label }: { slices: Slice[]; size?: number; centre: ReactNode; label: string }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const stroke = 16;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut">
      <div className="donut__ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} role="img" aria-label={label}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={stroke} />
          {slices.map((s) => {
            const len = (s.value / total) * c;
            const el = (
              <circle
                key={s.key}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={stroke}
                strokeDasharray={`${Math.max(0, len - 2)} ${c}`}
                strokeDashoffset={-offset}
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
              />
            );
            offset += len;
            return el;
          })}
        </svg>
        <div className="donut__centre">{centre}</div>
      </div>
      <ul className="donut__legend">
        {slices.map((s) => (
          <li key={s.key}>
            <span className="legend__swatch" style={{ background: s.color }} />
            <span className="donut__label">{s.label}</span>
            <span className="tabular donut__value">{s.value}</span>
            <span className="tabular subtle">{Math.round((s.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sparkline({ values, color = 'var(--chart-1)', width = 96, height = 28 }: { values: number[]; color?: string; width?: number; height?: number }) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const step = width / Math.max(1, values.length - 1);
  const pts = values.map((v, i) => `${i * step},${height - 2 - ((v - min) / (max - min || 1)) * (height - 4)}`);
  return (
    <svg className="sparkline" width={width} height={height} aria-hidden="true">
      <path d={`M${pts.join(' L')}`} fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function SegmentBar({ slices, label, legend = true }: { slices: Slice[]; label: string; legend?: boolean }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div className="segment-bar">
      <div className="segment-bar__track" role="img" aria-label={label}>
        {slices.map((s) =>
          s.value > 0 ? <span key={s.key} style={{ flexGrow: s.value, background: s.color } as CSSProperties} title={`${s.label}: ${s.value}`} /> : null,
        )}
      </div>
      {legend && (
        <ul className="legend legend--wrap">
          {slices.map((s) => (
            <li key={s.key}>
              <span className="legend__swatch" style={{ background: s.color }} />
              {s.label}
              <span className="tabular subtle">{Math.round((s.value / total) * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
