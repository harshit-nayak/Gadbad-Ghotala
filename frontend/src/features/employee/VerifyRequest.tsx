import { useEffect, useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../components/ui/Logo';
import { Pill } from '../../components/ui/Pill';
import { formatInr, formatTimeIst } from '../../domain/format';
import type { CallOutcome, VerificationMethod } from '../../domain/types';
import { incidentService } from '../../services/incidentService';
import { useDemo } from '../../state/DemoProvider';
import { firstName } from './signalCopy';
import { PRODUCT_NAME } from '../../app/brand';

type CallbackState = 'idle' | 'dialing' | 'connected';
const RESPONSE_DELAY_MS = 550;
const DIAL_MS = 1600;

export function VerifyRequest() {
  const { actions } = useDemo();
  const { claimedIdentity: caller, receiver, request } = incidentService.getActiveCall();
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [callback, setCallback] = useState<CallbackState>('idle');
  const name = firstName(caller.name);
  const amount = request.amountInr ? formatInr(request.amountInr) : request.description;

  useEffect(() => {
    if (callback !== 'dialing') return;
    const id = window.setTimeout(() => setCallback('connected'), DIAL_MS);
    return () => window.clearTimeout(id);
  }, [callback]);

  const respond = (key: string, outcome: CallOutcome, method: VerificationMethod) => {
    if (submitting) return;
    setSubmitting(key);
    window.setTimeout(() => actions.resolveCall(outcome, method), RESPONSE_DELAY_MS);
  };

  return (
    <div className="screen verify">
      <div className="verify__back">
        <Button variant="ghost" icon="chevronLeft" onClick={actions.showAlert}>
          Back to alert
        </Button>
      </div>

      <div>
        <h2 className="verify__title">Verify this request</h2>
        <p className="verify__lead">
          {PRODUCT_NAME} has asked the real {caller.name} to confirm. Don't act until you have an answer.
        </p>
      </div>

      <section className="request-card" aria-label="Request being verified">
        <div className="request-card__who">
          <span>Caller claims to be</span>
          <strong>
            {caller.name} ({caller.roleShort})
          </strong>
        </div>
        <div className="request-card__main">
          <span className="request-card__label">Request</span>
          <p className="request-card__amount tabular">{amount}</p>
          <p className="request-card__desc">
            {request.description}: {request.counterparty}
          </p>
          <p className="request-card__meta">
            <Icon name="clock" size={14} />
            Asked at {formatTimeIst(request.requestedAt)}, to be paid {request.deadline}
          </p>
        </div>
      </section>

      <section className="prompt-preview" aria-labelledby="prompt-question">
        <p className="prompt-preview__caption">
          <Icon name="device" size={14} />
          Sent to {name}'s registered device
          <Pill tone="analysis" className="presenter-only">Demo: answer as {name}</Pill>
        </p>
        <div className="prompt">
          <div className="prompt__top">
            <Logo compact />
            <span className="prompt__waiting">
              <span className="spinner spinner--sm" aria-hidden="true" />
              Waiting for reply
            </span>
          </div>
          <h3 id="prompt-question" className="prompt__question">
            Did you authorize this request?
          </h3>
          <p className="prompt__summary">
            {amount} to {request.counterparty}, requested on a call to {receiver.name} at {formatTimeIst(request.requestedAt)}.
          </p>
          <div className="prompt__actions">
            <Button
              variant="safe-outline"
              block
              icon="check"
              loading={submitting === 'yes'}
              disabled={!!submitting && submitting !== 'yes'}
              onClick={() => respond('yes', 'request_confirmed', 'claimed_person_device')}
            >
              Yes, I authorized it
            </Button>
            <Button
              variant="danger-outline"
              block
              icon="close"
              loading={submitting === 'no'}
              disabled={!!submitting && submitting !== 'no'}
              onClick={() => respond('no', 'impersonation_confirmed', 'claimed_person_device')}
            >
              No, this isn't me
            </Button>
          </div>
        </div>
      </section>

      <section className="alt-verify" aria-labelledby="alt-verify-heading">
        <h3 id="alt-verify-heading" className="alt-verify__heading">
          Other ways to verify
        </h3>
        <ul>
          <li>
            <button
              type="button"
              className="option-row"
              aria-expanded={callback !== 'idle'}
              onClick={() => setCallback((c) => (c === 'idle' ? 'dialing' : c))}
            >
              <span className="option-row__icon">
                <Icon name="callback" size={18} />
              </span>
              <span>
                <span className="option-row__title">Verify through official channel</span>
                <span className="option-row__sub tabular">Call back {caller.officialLine} from the company directory</span>
              </span>
              <Icon name="chevronRight" size={18} className="option-row__chevron" />
            </button>
            {callback !== 'idle' && (
              <div className="callback-panel" role="status">
                {callback === 'dialing' ? (
                  <p className="callback-panel__status">
                    <span className="spinner spinner--sm" aria-hidden="true" />
                    Calling the Office of the {caller.roleShort}. Put the current caller on hold.
                  </p>
                ) : (
                  <>
                    <p className="callback-panel__status">
                      <Icon name="phone" size={14} />
                      Connected. Did {name} make this request?
                    </p>
                    <div className="callback-panel__actions">
                      <Button
                        variant="danger-outline"
                        loading={submitting === 'cb-no'}
                        onClick={() => respond('cb-no', 'impersonation_confirmed', 'official_callback')}
                      >
                        He didn't
                      </Button>
                      <Button
                        variant="secondary"
                        loading={submitting === 'cb-yes'}
                        onClick={() => respond('cb-yes', 'request_confirmed', 'official_callback')}
                      >
                        He did
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}
          </li>
          <li>
            <button
              type="button"
              className="option-row"
              onClick={() => respond('security', 'escalated', 'security_team')}
              disabled={!!submitting}
            >
              <span className="option-row__icon">
                <Icon name="bell" size={18} />
              </span>
              <span>
                <span className="option-row__title">Notify Security Team</span>
                <span className="option-row__sub">Share this call with the fraud team and keep the request on hold</span>
              </span>
              <Icon name="chevronRight" size={18} className="option-row__chevron" />
            </button>
          </li>
        </ul>
      </section>
    </div>
  );
}
