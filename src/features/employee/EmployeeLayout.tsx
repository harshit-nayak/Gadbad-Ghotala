import { useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { employeeSteps, pathForStage } from '../../app/navigation';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../components/ui/Logo';
import { Pill, type Tone } from '../../components/ui/Pill';
import { incidentService } from '../../services/incidentService';
import { PRODUCT_NAME } from '../../app/brand';
import { useDemo } from '../../state/DemoProvider';
import type { CallStage } from '../../state/demoState';
import './employee.css';

const deviceStatus: Record<CallStage, { text: string; tone: Tone; live?: boolean }> = {
  incoming: { text: 'Protected', tone: 'safe' },
  declined: { text: 'Protected', tone: 'safe' },
  live: { text: 'Analysing call', tone: 'analysis', live: true },
  alert: { text: 'High risk', tone: 'risk', live: true },
  verify: { text: 'Verifying', tone: 'analysis', live: true },
  outcome: { text: 'Protected', tone: 'safe' },
};

export function EmployeeLayout() {
  const { state, actions } = useDemo();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const expectedPath = pathForStage[state.stage];

  useEffect(() => {
    if (pathname !== expectedPath) navigate(expectedPath, { replace: true });
  }, [pathname, expectedPath, navigate]);

  const { receiver: person } = incidentService.getActiveCall();
  const live = state.stage === 'live' || state.stage === 'alert' || state.stage === 'verify';
  const currentStep = employeeSteps.findIndex((step) => step.stages.includes(state.stage));
  const status = deviceStatus[state.stage];

  return (
    <div className="employee">
      <aside className="employee__rail" aria-label="Call context">
        <div>
          <p className="context__eyebrow">Signed in</p>
          <h1 className="context__headline">
            {person.name}
            <span className="context__role">{person.roleShort}, {person.location}</span>
          </h1>
          <p className="context__body">{PRODUCT_NAME} is protecting this call while you speak.</p>
        </div>

        <section className="context__panel" aria-label="Protection status">
          <header className="context__panel-head">
            <span className="context__panel-icon">
              <Icon name={live ? 'activity' : 'shieldCheck'} size={24} />
            </span>
            <div>
              <p className="context__panel-title">{live ? 'Live voice analysis' : 'Protection active'}</p>
              <p className="context__panel-sub">{live ? 'Checking the voice and the request' : 'Ready for incoming calls'}</p>
            </div>
          </header>

          <div className={`context__wave ${live ? 'is-live' : ''}`} aria-hidden="true">
            {Array.from({ length: 34 }, (_, i) => (
              <i
                key={i}
                style={{
                  height: `${18 + Math.abs(Math.sin(i * 0.8)) * 70}%`,
                  animationDelay: `${(i % 9) * 90}ms`,
                }}
              />
            ))}
          </div>

          <ul className="context__checks">
            {[
              { label: 'Voice authenticity', icon: 'fingerprint' as const },
              { label: 'Conversation signals', icon: 'activity' as const },
              { label: 'Request context', icon: 'shield' as const },
            ].map((check) => (
              <li key={check.label} className="context__check">
                <Icon name={check.icon} size={18} />
                <span>{check.label}</span>
                <span className="context__check-state">{live ? 'Checking' : 'Standing by'}</span>
              </li>
            ))}
          </ul>

          <p className="context__foot">
            <Icon name="lock" size={14} />
            Voice features are extracted on this work device and compared with trusted voice profiles held on company
            servers.
          </p>
        </section>

        <div className="flow presenter-only">
          <h2 className="flow__heading">Demo flow</h2>
          <ol className="flow__steps">
            {employeeSteps.map((step, index) => (
              <li
                key={step.label}
                className={`flow__step ${index < currentStep ? 'is-done' : ''} ${index === currentStep ? 'is-current' : ''}`}
              >
                <span className="flow__marker">
                  {index < currentStep ? <Icon name="check" size={13} strokeWidth={3} /> : index + 1}
                </span>
                <span className="flow__label">{step.label}</span>
              </li>
            ))}
          </ol>
          {state.stage === 'live' && (
            <Button variant="ghost" onClick={actions.showAlert}>
              Skip to alert
            </Button>
          )}
        </div>
      </aside>

      <div className="employee__stage">
        <div className="device" data-stage={state.stage}>
          <div className="device__bar">
            <Logo compact />
            <Pill tone={status.tone} dot={status.live ? 'live' : true}>
              {status.text}
            </Pill>
          </div>
          <div className="device__screen" key={pathname}>
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
