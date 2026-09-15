"""Turning per-window model scores into a decision and a session risk level.

Two design constraints from the project brief drive everything here:

1. **A false "this is a deepfake" is expensive.** Telling a genuine customer
   they sound synthetic destroys the trust the system exists to protect. So
   the verdict space has three bands, not two: a window that isn't clearly
   real and isn't clearly synthetic returns `uncertain`, which asks for
   verification rather than asserting fraud.

2. **A risk score has to update continuously, and survive one odd window.**
   Real calls produce the occasional low-scoring window from a codec glitch or
   a burst of noise. Session risk is therefore an exponential moving average
   over windows, and the high band additionally requires the suspicion to be
   *sustained* across consecutive windows.

The thresholds are configurable and their defaults are NOT calibrated. Derive
yours from the EER in deepfake/results/summary.json before trusting them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app import config

LABEL_REAL = "likely_real"
LABEL_SYNTHETIC = "likely_synthetic"
LABEL_UNCERTAIN = "uncertain"

BAND_LOW = "low"
BAND_ELEVATED = "elevated"
BAND_HIGH = "high"

# Band cutoffs on P(spoof), derived from the same thresholds used per window so
# the session view and the per-window view can never disagree in direction.
_HIGH_CUT = 1.0 - config.THRESHOLD_SYNTHETIC   # 0.70 by default
_ELEVATED_CUT = 1.0 - config.THRESHOLD_REAL    # 0.25 by default

RECOMMENDATIONS = {
    BAND_LOW: "No action. Nothing in the audio suggests synthesis.",
    BAND_ELEVATED: "Verify by a second channel before acting on this call "
                   "(call back on a known number, or ask for a second factor).",
    BAND_HIGH: "Do not act on instructions from this call. Escalate and "
               "verify the caller through an independent channel.",
}


def classify(p_bonafide: float) -> str:
    """Per-window label. The middle band is deliberately wide."""
    if p_bonafide >= config.THRESHOLD_REAL:
        return LABEL_REAL
    if p_bonafide <= config.THRESHOLD_SYNTHETIC:
        return LABEL_SYNTHETIC
    return LABEL_UNCERTAIN


@dataclass
class RiskTracker:
    """Running risk for one track across a session."""

    alpha: float = config.RISK_EMA_ALPHA
    sustain: int = config.RISK_SUSTAIN_WINDOWS

    risk: float = 0.0                  # EMA of P(spoof)
    n_windows: int = 0
    counts: dict = field(default_factory=lambda: {
        LABEL_REAL: 0, LABEL_SYNTHETIC: 0, LABEL_UNCERTAIN: 0
    })
    consecutive_synthetic: int = 0
    max_consecutive_synthetic: int = 0
    min_p_bonafide: float | None = None
    mean_p_bonafide: float = 0.0

    def update(self, p_bonafide: float) -> dict:
        label = classify(p_bonafide)
        p_spoof = 1.0 - p_bonafide

        self.n_windows += 1
        self.counts[label] += 1
        # Seed the EMA with the first observation rather than easing up from
        # zero, so an obviously synthetic opening window isn't reported as low.
        self.risk = p_spoof if self.n_windows == 1 else \
            (self.alpha * p_spoof + (1 - self.alpha) * self.risk)
        self.mean_p_bonafide += (p_bonafide - self.mean_p_bonafide) / self.n_windows
        self.min_p_bonafide = p_bonafide if self.min_p_bonafide is None \
            else min(self.min_p_bonafide, p_bonafide)

        if label == LABEL_SYNTHETIC:
            self.consecutive_synthetic += 1
            self.max_consecutive_synthetic = max(
                self.max_consecutive_synthetic, self.consecutive_synthetic
            )
        else:
            self.consecutive_synthetic = 0

        return {"label": label, **self.snapshot()}

    @property
    def band(self) -> str:
        if self.n_windows == 0:
            return BAND_LOW
        if self.consecutive_synthetic >= self.sustain or self.risk >= _HIGH_CUT:
            return BAND_HIGH
        if self.risk >= _ELEVATED_CUT:
            return BAND_ELEVATED
        return BAND_LOW

    def snapshot(self) -> dict:
        band = self.band
        return {
            "session_risk": round(self.risk, 4),
            "risk_band": band,
            "recommendation": RECOMMENDATIONS[band],
            "n_windows": self.n_windows,
            "consecutive_synthetic": self.consecutive_synthetic,
        }

    def summary(self) -> dict:
        return {
            **self.snapshot(),
            "counts": dict(self.counts),
            "max_consecutive_synthetic": self.max_consecutive_synthetic,
            "mean_p_bonafide": round(self.mean_p_bonafide, 4) if self.n_windows else None,
            "min_p_bonafide": round(self.min_p_bonafide, 4) if self.min_p_bonafide is not None else None,
            "thresholds": {
                "real": config.THRESHOLD_REAL,
                "synthetic": config.THRESHOLD_SYNTHETIC,
                "ema_alpha": self.alpha,
                "sustain_windows": self.sustain,
            },
        }
