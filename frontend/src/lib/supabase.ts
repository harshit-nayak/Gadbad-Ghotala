/**
 * Supabase client, used for sign-in (Google via Supabase Auth).
 *
 * Configured from frontend/.env.local:
 *   VITE_SUPABASE_URL=https://<project-ref>.supabase.co
 *   VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...   (or the legacy anon key)
 *
 * Both values are public by design; Row Level Security protects data. Without
 * them the client is null and the app runs without sign-in.
 *
 * PKCE flow: Google sends the user back with ?code=..., which supabase-js
 * exchanges for a session. The implicit flow would put tokens in the URL hash,
 * where they would collide with this app's hash routing.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const url: string | undefined = import.meta.env.VITE_SUPABASE_URL;
const key: string | undefined = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient | null =
  url && key
    ? createClient(url, key, {
        auth: { flowType: 'pkce', detectSessionInUrl: true, persistSession: true, autoRefreshToken: true },
      })
    : null;

export const isAuthConfigured = supabase !== null;
