import type { ReactNode } from 'react';
import './ui.css';

export type Tone = 'neutral' | 'brand' | 'analysis' | 'risk' | 'warn' | 'safe';

interface PillProps {
  tone?: Tone;
  /** Shows a status dot; `live` makes it pulse */
  dot?: boolean | 'live';
  children: ReactNode;
  className?: string;
}

export function Pill({ tone = 'neutral', dot = false, children, className = '' }: PillProps) {
  return (
    <span className={`pill pill--${tone} ${className}`}>
      {dot && <span className={`pill__dot ${dot === 'live' ? 'pill__dot--live' : ''}`} aria-hidden="true" />}
      {children}
    </span>
  );
}
