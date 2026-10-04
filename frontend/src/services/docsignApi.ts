/** Thin client for the docsign pipeline's HTTP API (see SIH/docPipeline/doc/src/docsign/web.py).
 * Requests go through the Vite dev proxy (/api, /root_ca.pem -> 127.0.0.1:8765). */

export type VerifyStatus =
  | 'VALID'
  | 'TAMPERED'
  | 'INVALID'
  | 'EXPIRED'
  | 'UNVERIFIABLE'
  | 'VERIFICATION_UNAVAILABLE';

export interface SignerInfo {
  employee_id: string | null;
  name: string | null;
  key_id: string | null;
  certificate: {
    status: string | null;
    serial: string | null;
    valid_from: string | null;
    valid_until: string | null;
  };
  signature: { algorithm: string; hash_algorithm: string; verified: boolean };
  timestamp: { present: boolean; trusted: boolean | null };
}

export interface VerifyResult {
  status: VerifyStatus;
  signature_found: boolean | null;
  failure_reason: string | null;
  document_hash: string | null;
  signers: SignerInfo[];
  reason: string | null;
  signer_name: string | null;
  signer_id: string | null;
  certificate_valid_until: string | null;
  document_digest: string | null;
  document: string | null;
}

export interface CaInfo {
  subject: string;
  not_before: string;
  not_after: string;
}

export interface EnrolledEmployee {
  id: string;
  name: string;
  email: string;
  not_before: string;
  not_after: string;
  enrolled_at: string;
  expired: boolean | null;
}

export interface StatusResponse {
  ca: CaInfo | null;
  enrolled: EnrolledEmployee[];
}

export interface SignatureHistoryEntry {
  id: number;
  filename: string | null;
  document_hash: string;
  employee_id: string;
  employee_name: string;
  certificate_serial: string | null;
  signed_at: string;
  source: string;
}

export interface HistoryResponse {
  records: SignatureHistoryEntry[];
}

export interface EnrolResult {
  ok: true;
  id: string;
  name: string;
  email: string;
  not_after: string;
}

export interface SignResult {
  status: 'SIGNED';
  ok: true;
  sig_filename: string;
  bundle_text: string;
  signer: string;
  digest: string;
  document_hash: string;
  signed_at: string;
  certificate_serial: string;
  registry: { ok: boolean; signature_id?: number; error?: string } | null;
}

export class DocsignApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function asJson<T>(res: Response): Promise<T> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // no JSON body
  }
  if (!res.ok) {
    const message = (body as { error?: string } | null)?.error ?? `Request failed (${res.status})`;
    throw new DocsignApiError(message, res.status);
  }
  return body as T;
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new DocsignApiError('Cannot reach the docsign service. Is it running?', 0);
  }
  return asJson<T>(res);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new DocsignApiError('Cannot reach the docsign service. Is it running?', 0);
  }
  return asJson<T>(res);
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method: 'POST', body: form });
  } catch {
    throw new DocsignApiError('Cannot reach the docsign service. Is it running?', 0);
  }
  return asJson<T>(res);
}

export const docsignApi = {
  status: () => getJson<StatusResponse>('/api/status'),

  history: () => getJson<HistoryResponse>('/api/history'),

  initCa: () => postJson<{ ok: true; ca: CaInfo }>('/api/init-ca', {}),

  enrol: (payload: { name: string; email: string; id: string }) =>
    postJson<EnrolResult>('/api/enrol', payload),

  sign: (employeeId: string, file: File) => {
    const form = new FormData();
    form.append('employee_id', employeeId);
    form.append('file', file);
    return postForm<SignResult>('/api/sign', form);
  },

  verify: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return postForm<VerifyResult>('/api/verify', form);
  },

  verifyOffline: (file: File, sig: File) => {
    const form = new FormData();
    form.append('file', file);
    form.append('sig', sig);
    return postForm<VerifyResult>('/api/verify/offline', form);
  },

  rootCaUrl: '/root_ca.pem',
};
