import './ui.css';
import { PRODUCT_NAME } from '../../app/brand';

/** GG mark: a voice line that resolves into a check. */
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`logo ${compact ? 'logo--compact' : ''}`}>
      <svg className="logo__mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <rect width="32" height="32" rx="9" className="logo__tile" />
        <path
          d="M6 16.5h3l2.2-5 3.3 10 3-7.5 2 3.5L26 9"
          fill="none"
          stroke="#fff"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="logo__word">{PRODUCT_NAME}</span>
    </span>
  );
}
