import { Avatar } from '../../components/ui/Avatar';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { incidentService } from '../../services/incidentService';
import { useDemo } from '../../state/DemoProvider';
import { PRODUCT_NAME } from '../../app/brand';

export function IncomingCall() {
  const { state, actions } = useDemo();
  const { claimedIdentity: caller, callerNumber, metadata } = incidentService.getActiveCall();

  if (state.stage === 'declined') {
    return (
      <div className="screen declined">
        <span className="declined__icon">
          <Icon name="phone" size={26} className="icon-hangup" />
        </span>
        <h2 className="declined__title">Call declined</h2>
        <p className="declined__body">
          You declined a call from {caller.name}. No audio was analysed.
        </p>
        <Button variant="secondary" icon="refresh" onClick={actions.resetDemo} className="presenter-only">
          Ring again
        </Button>
      </div>
    );
  }

  return (
    <div className="screen incoming">
      <p className="incoming__status">
        <Icon name="phone" size={14} />
        Incoming call, {metadata.direction} line
      </p>

      <div className="incoming__caller">
        <Avatar initials={caller.initials} size="xl" ringing />
        <h2 className="incoming__name">{caller.name}</h2>
        <p className="incoming__role">{caller.role}</p>
        <p className="incoming__number tabular">{callerNumber}</p>
      </div>

      <div className="protect-note">
        <span className="protect-note__icon">
          <Icon name="shieldCheck" size={22} />
        </span>
        <div>
          <p className="protect-note__title">{PRODUCT_NAME} is protecting this call</p>
          <p className="protect-note__body">
            The voice, and anything you are asked to do, will be checked while you talk.
          </p>
        </div>
      </div>

      <div className="incoming__actions">
        <button type="button" className="call-action call-action--decline" onClick={actions.declineCall}>
          <span className="call-action__circle">
            <Icon name="phone" size={26} className="icon-hangup" />
          </span>
          Decline
        </button>
        <button type="button" className="call-action call-action--accept" onClick={actions.acceptCall}>
          <span className="call-action__circle">
            <Icon name="phone" size={26} />
          </span>
          Accept
        </button>
      </div>
    </div>
  );
}
