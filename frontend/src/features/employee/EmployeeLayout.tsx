import { useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { employeeSteps, pathForStage } from '../../app/navigation';
import { Avatar } from '../../components/ui/Avatar';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../components/ui/Logo';
import { Pill, type Tone } from '../../components/ui/Pill';
import { incidentService } from '../../services/incidentService';
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

  const { receiver } = incidentService.getActiveCall();
  const currentStep = employeeSteps.findIndex((step) => step.stages.includes(state.stage));
  const status = deviceStatus[state.stage];

  return (
    <div className="employee">
      <aside className="employee__rail" aria-label="Call context">
        <div className="persona">
          <Avatar initials={receiver.initials} tone="plum" />
          <div>
            <h1 className="persona__name">{receiver.name}</h1>
            <p className="persona__role">
              {receiver.role}, {receiver.location}
            </p>
          </div>
        </div>

        <div className="flow presenter-only">
          <h2 className="flow__heading">Demo flow</h2>
          <ol className="flow__steps">
            {employeeSteps.map((step, index) => {
              const position = index < currentStep ? 'done' : index === currentStep ? 'current' : 'upcoming';
              return (
                <li key={step.label} className={`flow__step flow__step--${position}`} aria-current={position === 'current' ? 'step' : undefined}>
                  <span className="flow__marker" aria-hidden="true">
                    {position === 'done' ? <Icon name="check" size={12} strokeWidth={3} /> : index + 1}
                  </span>
                  <span className="flow__label">{step.label}</span>
                </li>
              );
            })}
          </ol>
          {state.stage === 'live' && (
            <Button variant="ghost" className="flow__skip" onClick={actions.showAlert}>
              Skip to alert
            </Button>
          )}
        </div>

        <p className="employee__note">
          <Icon name="lock" size={14} />
          Voice features are extracted on this work device and compared with trusted voice profiles held on company servers.
        </p>
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
