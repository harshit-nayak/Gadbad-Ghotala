import { Link } from 'react-router-dom';
import { PRODUCT_NAME } from '../../app/brand';
import { Icon } from '../../components/ui/Icon';
import { imagery } from './imagery';
import { scrollToId } from './scrollTo';
import './hero.css';

/**
 * Hero: a single layered canvas, not a column layout.
 *
 * The photograph is the full width of the section and dissolves into the ivory
 * page through a mask, so there is no image panel and no text panel. Type is
 * positioned over that canvas, the last headline line crossing onto the
 * photograph. The call read-out is pinned to the bottom edge of the same
 * canvas, away from the subject.
 */
export function Hero() {
  const photo = imagery.hero;

  return (
    <section className="gghero">
      <div className="gghero__canvas" aria-hidden="true">
        <img
          className="gghero__photo"
          src={photo.src}
          alt=""
          style={{ objectPosition: photo.focus }}
          onError={(e) => {
            const el = e.currentTarget;
            if (el.dataset.fallback !== 'used' && photo.fallback) {
              el.dataset.fallback = 'used';
              el.src = photo.fallback;
            }
          }}
        />
        <span className="gghero__dissolve" />
        <span className="gghero__grain" />
        <span className="gghero__stipple" />
      </div>

      <p className="gghero__marker" aria-hidden="true">
        01
      </p>
      <p className="gghero__vertical" aria-hidden="true">
        One call · One decision
      </p>

      <div className="gghero__type">
        <p className="gghero__kicker">
          Voice security
          <span className="gghero__rule" />
          Real-time protection
        </p>

        <h1 className="gghero__headline">
          <span className="l1">A familiar voice</span>
          <span className="l2">isn't proof</span>
          <span className="l3">of identity.</span>
        </h1>

        <div className="gghero__foot">
          <p className="gghero__lede">
            {PRODUCT_NAME} detects voice-cloning impersonation in real time and helps organisations verify high-risk
            requests before sensitive actions are taken.
          </p>
          <div className="gghero__actions">
            <a href="#how-it-works" className="btn btn--primary btn--lg" onClick={(e) => scrollToId(e, '#how-it-works')}>
              <span>Explore {PRODUCT_NAME}</span>
              <Icon name="arrowRight" size={19} />
            </a>
            <Link to="/login" className="btn btn--secondary btn--lg">
              <span>Login</span>
            </Link>
          </div>
        </div>
      </div>

      <aside className="gghero__readout" aria-hidden="true">
        <p className="gghero__readout-top">
          <Icon name="phone" size={12} />
          Incoming call
          <span className="gghero__live" />
        </p>
        <p className="gghero__caller">Rahul Sharma</p>
        <p className="gghero__role">Chief Executive Officer</p>
        <dl className="gghero__facts">
          <div>
            <dt>Request</dt>
            <dd>Urgent financial transfer</dd>
          </div>
          <div>
            <dt>Risk</dt>
            <dd className="is-high">High</dd>
          </div>
        </dl>
        <p className="gghero__verify">Verification required</p>
      </aside>
    </section>
  );
}
