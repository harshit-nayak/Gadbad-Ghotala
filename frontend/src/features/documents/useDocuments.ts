import { useCallback, useEffect, useRef, useState } from 'react';
import { docsignApi, type StatusResponse } from '../../services/docsignApi';
import { useCurrentUser } from '../../hooks/useCurrentUser';

/** Polls the docsign pipeline's /api/status — root CA info and enrolled employees.
 * Automatically enrols the current user (from Supabase Google Auth) if not already enrolled.
 */
export function useDocsignStatus() {
  const currentUser = useCurrentUser();
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoEnrolling, setAutoEnrolling] = useState(false);
  const autoEnrolledRef = useRef(false);

  const refresh = useCallback(async (): Promise<StatusResponse | null> => {
    try {
      const data = await docsignApi.status();
      setStatus(data);
      setError(null);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach the docsign service.');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Automatically enrol user from Supabase Google Auth in the document pipeline
  useEffect(() => {
    if (!currentUser.name || autoEnrolledRef.current) return;

    let active = true;

    async function ensureUserEnrolled() {
      try {
        const currentStatus = await docsignApi.status();
        if (!active || !currentStatus) return;

        // Initialise Root CA if missing
        if (!currentStatus.ca) {
          try {
            await docsignApi.initCa();
          } catch {
            // may already be init
          }
        }

        const emailLower = (currentUser.email || '').toLowerCase();
        const isEnrolled = currentStatus.enrolled.some(
          (e) => (emailLower && e.email.toLowerCase() === emailLower) || e.id === currentUser.id
        );

        if (!isEnrolled) {
          setAutoEnrolling(true);
          await docsignApi.enrol({
            name: currentUser.name,
            email: currentUser.email || `${currentUser.id}@company.internal`,
            id: currentUser.id,
          });
          autoEnrolledRef.current = true;
          if (active) {
            await refresh();
          }
        } else {
          autoEnrolledRef.current = true;
        }
      } catch (err) {
        // Backend not running or already enrolled
        console.debug('Docsign auto-enrol check:', err);
      } finally {
        if (active) {
          setAutoEnrolling(false);
        }
      }
    }

    ensureUserEnrolled();

    return () => {
      active = false;
    };
  }, [currentUser.name, currentUser.email, currentUser.id, refresh]);

  return { status, error, loading, autoEnrolling, refresh };
}
