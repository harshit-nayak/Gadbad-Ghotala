import { useEffect, useRef } from 'react';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import './viz.css';

export type WaveTone = 'calm' | 'rising' | 'risk' | 'safe' | 'muted';

interface WaveformProps {
  /** Accessible description of what the waveform represents */
  label: string;
  tone?: WaveTone;
  active?: boolean;
  height?: number;
}

const hash = (n: number) => {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};

/**
 * Speech-like animated waveform on canvas. Colours come from CSS custom
 * properties (--wave-a / --wave-b) set by the tone class, so themes apply.
 */
export function Waveform({ label, tone = 'calm', active = true, height = 64 }: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = 0;
    let frame = 0;
    const styles = getComputedStyle(canvas);
    const colorA = styles.getPropertyValue('--wave-a').trim() || '#8f77ec';
    const colorB = styles.getPropertyValue('--wave-b').trim() || '#d6336c';

    const resize = () => {
      width = canvas.clientWidth;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (time: number) => {
      const t = time / 1000;
      const bar = 3;
      const gap = 2.5;
      const count = Math.floor(width / (bar + gap));
      const mid = height / 2;
      const gradient = ctx.createLinearGradient(0, 0, width, 0);
      gradient.addColorStop(0, colorA);
      gradient.addColorStop(1, colorB);

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = gradient;
      ctx.beginPath();
      const tick = Math.floor(t * 12);
      for (let i = 0; i < count; i++) {
        const edge = Math.pow(Math.sin((Math.PI * (i + 0.5)) / count), 0.5);
        const phrase = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * 1.1 + i * 0.05));
        const syllable =
          Math.pow(Math.abs(Math.sin(t * 5.4 + i * 0.29)), 0.7) *
          (0.55 + 0.45 * Math.abs(Math.sin(t * 2.1 + i * 0.12 + 1.7)));
        const grain = 0.7 + 0.3 * hash(i + tick * 0.37);
        const amplitude = active ? 0.12 + 0.88 * syllable * phrase * grain : 0.05 + 0.03 * grain;
        const h = Math.max(2, amplitude * edge * (height - 6));
        const x = i * (bar + gap);
        if (typeof ctx.roundRect === 'function') ctx.roundRect(x, mid - h / 2, bar, h, 1.5);
        else ctx.rect(x, mid - h / 2, bar, h);
      }
      ctx.fill();
      if (!reducedMotion) frame = requestAnimationFrame(draw);
    };

    resize();
    const observer = new ResizeObserver(() => {
      resize();
      if (reducedMotion) draw(1800);
    });
    observer.observe(canvas);
    frame = requestAnimationFrame(reducedMotion ? () => draw(1800) : draw);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [tone, active, height, reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      className={`waveform waveform--${tone}`}
      style={{ height }}
      role="img"
      aria-label={label}
    />
  );
}
