import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { useNavigate } from 'react-router-dom';
import './videoCheck.css';

export function VideoCheck() {
  const navigate = useNavigate();

  return (
    <div className="video-check workspace-page">
      <PageHeader
        title="Video Analysis"
        eyebrow="Deepfake Video Forensics"
        description="Frame-level face-swap detection, temporal consistency scoring and GAN artifact inspection."
        actions={
          <Pill tone="warn" dot="live">
            Coming Soon
          </Pill>
        }
      />

      <div className="video-check__grid">
        <Panel className="video-check__hero-card">
          <div className="video-check__mockup">
            <div className="video-check__frame-box">
              <div className="video-check__scan-line" />
              <div className="video-check__face-target">
                <span className="video-check__corner video-check__corner--tl" />
                <span className="video-check__corner video-check__corner--tr" />
                <span className="video-check__corner video-check__corner--bl" />
                <span className="video-check__corner video-check__corner--br" />
                <span className="video-check__tag">FACE #01 · GAN ARTIFACT DETECTED</span>
              </div>
              <div className="video-check__meta-bar">
                <span>FPS: 30 · 1080p</span>
                <span>Model: Spatio-Temporal ResNet-50</span>
                <span>P(Real): 0.12 (Synthetic)</span>
              </div>
            </div>
          </div>

          <div className="video-check__info">
            <div className="video-check__badge">
              <Icon name="activity" size={16} />
              <span>Under Active Development</span>
            </div>
            <h2>Next-Gen Video Deepfake Detection</h2>
            <p>
              Video deepfakes are becoming weaponised in CEO impersonation calls and virtual kidnapping scams. Our upcoming video forensic pipeline processes video streams frame-by-frame to expose lip-sync anomalies, face blending boundaries, and unnatural blink frequencies.
            </p>

            <div className="video-check__features-list">
              <div className="video-check__feature-item">
                <Icon name="shieldCheck" size={18} />
                <div>
                  <strong>Face-Swap & Morphing Detection</strong>
                  <p>Catches pixel disparities and boundary blending artifacts around the jawline and eyes.</p>
                </div>
              </div>
              <div className="video-check__feature-item">
                <Icon name="activity" size={18} />
                <div>
                  <strong>Temporal Coherence Scoring</strong>
                  <p>Tracks inter-frame jitter and unnatural lighting changes across video sequences.</p>
                </div>
              </div>
              <div className="video-check__feature-item">
                <Icon name="fileText" size={18} />
                <div>
                  <strong>Forensic Heatmaps</strong>
                  <p>Generates downloadable per-frame anomaly heatmaps for compliance and court-admissible audit reports.</p>
                </div>
              </div>
            </div>

            <div className="video-check__actions">
              <Button variant="primary" icon="voice" onClick={() => navigate('/security/audio')}>
                Try Audio Check Now
              </Button>
              <Button variant="ghost" icon="shieldCheck" onClick={() => navigate('/documents')}>
                Verify Documents
              </Button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
