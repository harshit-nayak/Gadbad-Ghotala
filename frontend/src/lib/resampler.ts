/**
 * Streaming windowed-sinc resampler: blocks of float audio at the device rate
 * in (44.1 or 48 kHz from a browser mic), 16 kHz out, with no clicks or
 * aliasing at block boundaries.
 *
 * Each output sample is a low-pass-filtered interpolation over HALF_WIDTH input
 * samples on BOTH sides of its position. So an output can only be produced
 * once the input after it has arrived: the resampler keeps a tail of input
 * across calls and delays its output by HALF_WIDTH input samples (~1 ms),
 * rather than filtering each block on its own, which would smear every block
 * edge (the same trap as scipy's resample_poly on independent chunks).
 */

/** Low-pass cutoff as a fraction of the OUTPUT Nyquist: 0.9 of 8 kHz = 7.2 kHz. */
const CUTOFF = 0.9;
/** Sinc zero crossings kept on each side of the centre tap. */
const ZERO_CROSSINGS = 16;

export class StreamingResampler {
  private readonly step: number;
  private readonly fc: number;
  private readonly halfWidth: number;
  private buffer: Float32Array;
  /** Absolute input index of buffer[0]. */
  private base: number;
  /** Absolute input position of the next output sample. */
  private outIndex = 0;

  constructor(inRate: number, outRate: number) {
    this.step = inRate / outRate;
    // Cutoff in cycles per INPUT sample. When upsampling there's nothing to
    // anti-alias, so the cutoff stays at the input's own Nyquist.
    this.fc = (CUTOFF * 0.5 * Math.min(inRate, outRate)) / inRate;
    this.halfWidth = Math.ceil(ZERO_CROSSINGS / (2 * this.fc));
    // Pretend the stream was preceded by silence, so the first outputs have a
    // full kernel to read from.
    this.buffer = new Float32Array(this.halfWidth + 1);
    this.base = -this.buffer.length;
  }

  private kernel(x: number): number {
    if (Math.abs(x) > this.halfWidth) return 0;
    const arg = 2 * this.fc * x;
    const sinc = x === 0 ? 1 : Math.sin(Math.PI * arg) / (Math.PI * arg);
    // Blackman window over [-halfWidth, halfWidth].
    const w = (x + this.halfWidth) / (2 * this.halfWidth);
    const blackman = 0.42 - 0.5 * Math.cos(2 * Math.PI * w) + 0.08 * Math.cos(4 * Math.PI * w);
    return sinc * blackman;
  }

  /** Feed the next block of input; returns every output sample now computable. */
  push(input: Float32Array): Float32Array {
    const joined = new Float32Array(this.buffer.length + input.length);
    joined.set(this.buffer);
    joined.set(input, this.buffer.length);
    this.buffer = joined;
    const end = this.base + joined.length; // one past the last absolute input index

    const out: number[] = [];
    while (this.outIndex + this.halfWidth < end) {
      const t = this.outIndex;
      const first = Math.ceil(t - this.halfWidth);
      const last = Math.floor(t + this.halfWidth);
      let acc = 0;
      let weight = 0;
      for (let k = first; k <= last; k++) {
        const h = this.kernel(t - k);
        acc += joined[k - this.base] * h;
        weight += h;
      }
      // Normalising by the summed taps keeps DC gain at exactly 1 for any
      // fractional position (44.1 -> 16 kHz isn't an integer ratio).
      out.push(weight ? acc / weight : 0);
      this.outIndex += this.step;
    }

    // Drop input no future output can reach.
    const keepFrom = Math.max(this.base, Math.floor(this.outIndex - this.halfWidth) - 1);
    this.buffer = joined.slice(keepFrom - this.base);
    this.base = keepFrom;
    return Float32Array.from(out);
  }
}

/** [-1, 1] floats to little-endian PCM16, the backend's wire format. */
export function floatToPcm16(samples: Float32Array): Int16Array<ArrayBuffer> {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}
