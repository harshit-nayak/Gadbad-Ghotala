import { useCallback, useEffect, useState } from 'react';
import { docsignApi, type StatusResponse } from '../../services/docsignApi';

/** Polls the docsign pipeline's /api/status — root CA info and enrolled employees. */
export function useDocsignStatus() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await docsignApi.status();
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach the docsign service.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { status, error, loading, refresh };
}
