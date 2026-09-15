import type { ReactNode } from 'react';
import { imagery, type ImageKey } from './imagery';
import './editorial.css';

interface EditorialProps {
  slot: ImageKey;
  className?: string;
  /** Content layered over the photograph, e.g. a case number. */
  children?: ReactNode;
  priority?: boolean;
}

/**
 * A photograph with the shared editorial treatment: warm muting, grain and an
 * optional overlay. If the image fails to load the frame stays as a warm block
 * rather than showing a broken image.
 */
export function Editorial({ slot, className = '', children, priority = false }: EditorialProps) {
  const image = imagery[slot];
  return (
    <figure className={`edit ${className}`}>
      <img
        className="edit__photo"
        src={image.src}
        alt={image.alt}
        style={image.focus ? { objectPosition: image.focus } : undefined}
        loading={priority ? 'eager' : 'lazy'}
        onError={(e) => {
          const el = e.currentTarget;
          if (el.dataset.fallback !== 'used' && image.fallback) {
            el.dataset.fallback = 'used';
            el.src = image.fallback;
          }
        }}
      />
      <span className="edit__grain" aria-hidden="true" />
      {children && <figcaption className="edit__overlay">{children}</figcaption>}
    </figure>
  );
}
