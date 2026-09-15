import './incident.css';

/** Display projection of a voice embedding as a stable visual fingerprint. */
export function EmbeddingGrid({ values, label, tone = 'analysis', columns = 16 }: { values: number[]; label: string; tone?: 'analysis' | 'risk'; columns?: number }) {
  return (
    <div className={`embedding embedding--${tone}`} style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }} role="img" aria-label={label}>
      {values.map((v, i) => (
        <span key={i} style={{ opacity: 0.12 + v * 0.88 }} />
      ))}
    </div>
  );
}
