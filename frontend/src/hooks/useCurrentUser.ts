import { useAuth } from '../state/AuthProvider';

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  initials: string;
  avatarUrl?: string;
  role: string;
  department: string;
  location: string;
  isAuthenticated: boolean;
}

export function useCurrentUser(): CurrentUser {
  const { user } = useAuth();

  if (user) {
    const metadata = user.user_metadata ?? {};
    const name: string =
      metadata.full_name ||
      metadata.name ||
      user.email?.split('@')[0] ||
      'Authorized User';

    const email: string = user.email || '';
    const avatarUrl: string | undefined = metadata.avatar_url || metadata.picture;

    const initials =
      name
        .split(' ')
        .filter(Boolean)
        .map((part) => part[0])
        .join('')
        .slice(0, 2)
        .toUpperCase() || 'AU';

    // Stable 6-character employee ID derived from Supabase UID
    const empId = `emp-${user.id.replace(/-/g, '').slice(0, 6)}`;

    return {
      id: empId,
      name,
      email,
      initials,
      avatarUrl,
      role: 'Security Analyst & Fraud Lead',
      department: 'Fraud Operations & Risk',
      location: 'Mumbai HQ',
      isAuthenticated: true,
    };
  }

  // Fallback for unauthenticated local demo
  return {
    id: 'emp-demo',
    name: 'Demo Analyst',
    email: 'analyst@pehchaan.ai',
    initials: 'DA',
    role: 'Fraud Analyst',
    department: 'Fraud Operations',
    location: 'Mumbai HQ',
    isAuthenticated: false,
  };
}
