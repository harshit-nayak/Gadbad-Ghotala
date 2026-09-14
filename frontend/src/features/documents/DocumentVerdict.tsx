import { Icon, type IconName } from '../../components/ui/Icon';
import type { VerifyResult } from '../../services/docsignApi';

const STATUS_META: Record<VerifyResult['status'], { tone: string; label: string; icon: IconName }> = {
  VALID: { tone: 'safe', label: 'Valid', icon: 'check' },
  TAMPERED: { tone: 'risk', label: 'Tampered', icon: 'close' },
  INVALID: { tone: 'risk', label: 'Invalid', icon: 'close' },
  EXPIRED: { tone: 'warn', label: 'Expired', icon: 'alert' },
  UNVERIFIABLE: { tone: 'neutral', label: 'Unverifiable', icon: 'alert' },
  VERIFICATION_UNAVAILABLE: { tone: 'warn', label: 'Verification unavailable', icon: 'alert' },
};

export function DocumentVerdict({ result }: { result: VerifyResult }) {
  const meta = STATUS_META[result.status] ?? STATUS_META.UNVERIFIABLE;
  const signers = result.signers?.length
    ? result.signers.map((s) => ({ name: s.name, employee_id: s.employee_id }))
    : result.signer_name || result.signer_id
      ? [{ name: result.signer_name, employee_id: result.signer_id }]
      : [];
  const hash = result.document_hash || result.document_digest;

  return (
    <div className={`verdict verdict--${meta.tone}`}>
      <div className="verdict__head">
        <Icon name={meta.icon} size={18} />
        <h3>{meta.label}</h3>
      </div>
      {signers.map((s, i) => (
        <p key={i} className="verdict__line">
          Signed by {s.name || 'unknown'}
          {s.employee_id ? ` (${s.employee_id})` : ''}
        </p>
      ))}
      {result.certificate_valid_until && (
        <p className="verdict__line">Certificate valid until {result.certificate_valid_until}</p>
      )}
      {result.reason && <p className="verdict__line">{result.reason}</p>}
      {hash && (
        <p className="verdict__hash">
          <code>SHA-256 {hash}</code>
        </p>
      )}
    </div>
  );
}
