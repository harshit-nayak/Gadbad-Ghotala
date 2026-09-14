import './ui.css';

interface AvatarProps {
  initials: string;
  size?: 'sm' | 'md' | 'xl';
  tone?: 'lilac' | 'rose' | 'plum';
  /** Concentric rings for ringing state */
  ringing?: boolean;
}

export function Avatar({ initials, size = 'md', tone = 'lilac', ringing = false }: AvatarProps) {
  return (
    <span className={`avatar avatar--${size} avatar--${tone} ${ringing ? 'avatar--ringing' : ''}`} aria-hidden="true">
      {ringing && (
        <>
          <span className="avatar__ring" />
          <span className="avatar__ring avatar__ring--late" />
        </>
      )}
      <span className="avatar__initials">{initials}</span>
    </span>
  );
}
