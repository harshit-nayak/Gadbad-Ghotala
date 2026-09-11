import type { ReactNode } from 'react';
import { Sparkline } from '../charts/Charts';
import './metrics.css';

export interface KpiItem {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  spark?: number[];
  tone?: 'default' | 'risk' | 'warn' | 'safe' | 'brand';
}

const sparkColor = {
  default: 'var(--chart-1)',
  brand: 'var(--brand)',
  risk: 'var(--risk)',
  warn: 'var(--warn)',
  safe: 'var(--safe)',
};

/** A row of headline metrics in one surface, separated by hairlines. */
export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <dl className="kpis">
      {items.map((item) => (
        <div key={item.label} className={`kpi kpi--${item.tone ?? 'default'}`}>
          <dt className="kpi__label">{item.label}</dt>
          <dd className="kpi__value tabular">{item.value}</dd>
          <dd className="kpi__foot">
            {item.sub && <span className="kpi__sub">{item.sub}</span>}
            {item.spark && <Sparkline values={item.spark} color={sparkColor[item.tone ?? 'default']} width={72} height={22} />}
          </dd>
        </div>
      ))}
    </dl>
  );
}
