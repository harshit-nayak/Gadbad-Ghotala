#!/usr/bin/env python3
"""
evaluate_model.py  -  Evaluate XLSR-Mamba on ASVspoof5 datasets.

Pure-PyTorch Mamba SSM implementation (no mamba_ssm CUDA extensions).
Reconstructs the XLSR wav2vec-2.0 backbone from fairseq_src (no xlsr2_300m.pt needed).

Usage:
  python evaluate_model.py --max_samples 100          # quick smoke-test
  python evaluate_model.py --device cuda              # full eval on GPU
  python evaluate_model.py --tsv ASVspoof5.dev.track_1.tsv --flac_dir flac_D
"""

import sys, os, math, argparse, warnings
from dataclasses import dataclass, field
from functools import partial
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import soundfile as sf
from torch.utils.data import Dataset, DataLoader
from safetensors.torch import load_file
from tqdm import tqdm

warnings.filterwarnings('ignore')
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'fairseq_src'))


# ============================================================
# 1.  PURE-PYTORCH SELECTIVE SCAN
# ============================================================

def selective_scan_ref(u, delta, A, B, C,
                       D=None, z=None,
                       delta_bias=None, delta_softplus=False):
    dtype_in = u.dtype
    u = u.float()
    delta = delta.float()
    if delta_bias is not None:
        delta = delta + delta_bias[..., None].float()
    if delta_softplus:
        delta = F.softplus(delta)
    B_f = B.float()
    C_f = C.float()
    x = torch.zeros(u.shape[0], A.shape[0], A.shape[1],
                    device=u.device, dtype=torch.float32)
    deltaA   = torch.exp(torch.einsum('bdl,dn->bdln', delta, A.float()))
    deltaB_u = torch.einsum('bdl,bnl,bdl->bdln', delta, B_f, u)
    ys = []
    for t in range(u.shape[2]):
        x = deltaA[:, :, t] * x + deltaB_u[:, :, t]
        ys.append(torch.einsum('bdn,bn->bd', x, C_f[:, :, t]))
    y = torch.stack(ys, dim=2)
    out = y if D is None else y + u * D.float()[None, :, None]
    if z is not None:
        out = out * F.silu(z.float())
    return out.to(dtype_in)


# ============================================================
# 2.  MAMBA LAYER
# ============================================================

class RMSNorm(nn.Module):
    def __init__(self, d, eps=1e-5, **kwargs):
        super().__init__()
        self.eps    = eps
        self.weight = nn.Parameter(torch.ones(d))
    def forward(self, x):
        ms = x.float().pow(2).mean(-1, keepdim=True)
        return (x.float() * (ms + self.eps).rsqrt()).to(x.dtype) * self.weight


class Mamba(nn.Module):
    def __init__(self, d_model, d_state=16, d_conv=4, expand=2,
                 dt_rank='auto', conv_bias=True, bias=False,
                 use_fast_path=False, layer_idx=None, device=None, dtype=None):
        super().__init__()
        self.d_model = d_model
        self.d_inner = int(expand * d_model)
        self.d_state = d_state
        self.d_conv  = d_conv
        self.dt_rank = math.ceil(d_model / 16) if dt_rank == 'auto' else dt_rank
        fkw = {'device': device, 'dtype': dtype}
        self.in_proj  = nn.Linear(d_model, self.d_inner * 2, bias=bias, **fkw)
        self.conv1d   = nn.Conv1d(self.d_inner, self.d_inner, kernel_size=d_conv,
                                   groups=self.d_inner, padding=d_conv-1,
                                   bias=conv_bias, **fkw)
        self.x_proj   = nn.Linear(self.d_inner, self.dt_rank + d_state*2,
                                   bias=False, **fkw)
        self.dt_proj  = nn.Linear(self.dt_rank, self.d_inner, bias=True, **fkw)
        self.A_log    = nn.Parameter(torch.zeros(self.d_inner, d_state, **fkw))
        self.D        = nn.Parameter(torch.ones(self.d_inner, **fkw))
        self.out_proj = nn.Linear(self.d_inner, d_model, bias=bias, **fkw)
        self.act = nn.SiLU()

    def forward(self, h, inference_params=None):
        B, L, _ = h.shape
        xz = self.in_proj(h).transpose(1, 2)
        x, z = xz.chunk(2, dim=1)
        x = self.act(self.conv1d(x)[..., :L])
        xd = self.x_proj(x.transpose(1,2).reshape(B*L, self.d_inner))
        dt, Bm, Cm = torch.split(xd, [self.dt_rank, self.d_state, self.d_state], -1)
        dt = F.linear(dt, self.dt_proj.weight).reshape(B, L, self.d_inner).transpose(1,2)
        Bm = Bm.reshape(B, L, self.d_state).transpose(1, 2)
        Cm = Cm.reshape(B, L, self.d_state).transpose(1, 2)
        A  = -torch.exp(self.A_log.float())
        y  = selective_scan_ref(x, dt, A, Bm, Cm, D=self.D, z=z,
                                delta_bias=self.dt_proj.bias.float(),
                                delta_softplus=True)
        return self.out_proj(y.transpose(1, 2))


class Block(nn.Module):
    def __init__(self, dim, mixer_cls, norm_cls=nn.LayerNorm, **kw):
        super().__init__()
        self.mixer = mixer_cls(dim)
        self.norm  = norm_cls(dim)
    def forward(self, h, residual=None, inference_params=None):
        residual = (h + residual) if residual is not None else h
        h = self.norm(residual.to(self.norm.weight.dtype))
        return self.mixer(h, inference_params=inference_params), residual


def _make_block(d_model, rms_norm, norm_eps, layer_idx, device, dtype):
    fkw = {'device': device, 'dtype': dtype}
    mc  = partial(Mamba, layer_idx=layer_idx, **fkw)
    nc  = partial(RMSNorm if rms_norm else nn.LayerNorm, eps=norm_eps, **fkw)
    blk = Block(d_model, mc, norm_cls=nc)
    blk.layer_idx = layer_idx
    return blk


# ============================================================
# 3.  DUAL-COLUMN BIDIRECTIONAL MIXER MODEL
# ============================================================

class MixerModel(nn.Module):
    def __init__(self, d_model, n_layer, ssm_cfg=None, norm_epsilon=1e-5,
                 rms_norm=False, if_bidirectional=True, initializer_cfg=None,
                 fused_add_norm=False, residual_in_fp32=False,
                 device=None, dtype=None):
        super().__init__()
        self.if_bidirectional = if_bidirectional
        fkw = {'device': device, 'dtype': dtype}
        blk = partial(_make_block, d_model, rms_norm, norm_epsilon,
                      device=device, dtype=dtype)
        self.forward_layers  = nn.ModuleList([blk(layer_idx=i) for i in range(n_layer)])
        self.backward_layers = nn.ModuleList([blk(layer_idx=i) for i in range(n_layer)])
        nc = RMSNorm if rms_norm else nn.LayerNorm
        self.norm_f           = nc(d_model, eps=norm_epsilon, **fkw)
        self.f_attention_pool = nn.Linear(d_model, 1, **fkw)
        self.b_attention_pool = nn.Linear(d_model, 1, **fkw)
        self.LL               = nn.Linear(d_model*2, d_model, **fkw)
        self.dropout          = nn.Dropout(p=0.1)
        self.classifier       = nn.Linear(d_model, 2, **fkw)

    @staticmethod
    def _pool(pool, h):
        w = F.softmax(pool(h), dim=1)
        return (w.transpose(-1,-2) @ h).squeeze(-2)

    def _norm(self, _last_h, res, orig):
        r = (res + orig) if res is not None else orig
        return self.norm_f(r.to(self.norm_f.weight.dtype))

    def forward(self, x, inference_params=None):
        orig = self.dropout(x)
        if not self.if_bidirectional:
            h, res = orig, None
            for lyr in self.forward_layers:
                h, res = lyr(h, res, inference_params)
            h = self._norm(h, res, orig)
            return self.classifier(self.dropout(self._pool(self.f_attention_pool, h)))
        fh, fr = orig, None
        for lyr in self.forward_layers:
            fh, fr = lyr(fh, fr, inference_params)
        bh, br = orig.flip([1]), None
        for lyr in self.backward_layers:
            bh, br = lyr(bh, br, inference_params)
        fh = self._norm(fh, fr, orig)
        bh = self._norm(bh, br, orig)
        fp = self._pool(self.f_attention_pool, fh)
        bp = self._pool(self.b_attention_pool, bh)
        return self.classifier(self.dropout(self.LL(torch.cat([fp, bp], dim=1))))


# ============================================================
# 4.  SSL BACKBONE (XLSR wav2vec 2.0 from config)
# ============================================================

class SSLModel(nn.Module):
    def __init__(self):
        super().__init__()
        from fairseq.models.wav2vec.wav2vec2 import Wav2Vec2Config, Wav2Vec2Model
        cfg = Wav2Vec2Config(
            encoder_layers=24, encoder_embed_dim=1024,
            encoder_ffn_embed_dim=4096, encoder_attention_heads=16,
            conv_pos=128, conv_pos_groups=16,
            final_dim=768, latent_vars=320, latent_groups=2, latent_dim=0,
            layer_norm_first=True, extractor_mode='layer_norm',
            conv_bias=True, quantize_targets=True,
        )
        self.model   = Wav2Vec2Model(cfg)
        self.out_dim = 1024

    def extract_feat(self, wav):
        if wav.ndim == 3:
            wav = wav[:, :, 0]
        out = self.model(wav, mask=False, features_only=True)
        return out['x'], out['layer_results']


# ============================================================
# 5.  FULL MODEL
# ============================================================

@dataclass
class MambaConfig:
    d_model:          int  = 64
    n_layer:          int  = 6
    ssm_cfg:          dict = field(default_factory=dict)
    rms_norm:         bool = True
    residual_in_fp32: bool = True
    fused_add_norm:   bool = True


class Model(nn.Module):
    # num_encoders=12 -> n_layer=6 per direction, matching main.py's default
    # and the 6 forward/backward layer groups present in model.safetensors.
    def __init__(self, emb_size=144, num_encoders=12):
        super().__init__()
        self.ssl_model = SSLModel()
        self.LL        = nn.Linear(1024, emb_size)
        self.first_bn  = nn.BatchNorm2d(num_features=1)
        self.selu      = nn.SELU(inplace=True)
        cfg = MambaConfig(d_model=emb_size, n_layer=num_encoders // 2)
        self.conformer = MixerModel(
            d_model=cfg.d_model, n_layer=cfg.n_layer, ssm_cfg=cfg.ssm_cfg,
            rms_norm=cfg.rms_norm, residual_in_fp32=cfg.residual_in_fp32,
            fused_add_norm=cfg.fused_add_norm,
        )

    def forward(self, x):
        feat, _ = self.ssl_model.extract_feat(x)
        x = self.LL(feat)
        x = self.selu(self.first_bn(x.unsqueeze(1))).squeeze(1)
        return self.conformer(x)


# ============================================================
# 6.  DATASET
# ============================================================

def pad_or_trim(x, cut=66800):
    """Match XLSR_Mamba_repo/utils.py:pad - repeat-tile short clips, don't zero-pad."""
    if len(x) >= cut:
        return x[:cut]
    num_repeats = int(cut / len(x)) + 1
    return np.tile(x, num_repeats)[:cut]


class ASVspoofDataset(Dataset):
    def __init__(self, tsv_path, flac_dir, cut=66800, max_samples=None, seed=None):
        self.cut     = cut
        self.samples = []
        missing      = 0
        with open(tsv_path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 9:
                    continue
                utt_id = parts[1]
                label  = 1 if parts[8] == 'bonafide' else 0
                path   = os.path.join(flac_dir, utt_id + '.flac')
                if os.path.exists(path):
                    self.samples.append((utt_id, path, label))
                else:
                    missing += 1
        n_avail = len(self.samples)
        if max_samples and max_samples < n_avail:
            if seed is None:
                self.samples = self.samples[:max_samples]
            else:
                # The TSV is grouped by speaker/attack, so the first N rows are
                # not a representative subset. Sample uniformly instead.
                rng = np.random.default_rng(seed)
                idx = rng.choice(n_avail, size=max_samples, replace=False)
                self.samples = [self.samples[i] for i in sorted(idx)]
        n = len(self.samples)
        n_bon = sum(s[2] for s in self.samples)
        print(f'  Dataset: {n_avail} samples found ({missing} missing flac files)')
        print(f'  Using  : {n} samples (bonafide {n_bon}  spoof {n - n_bon})')

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        utt_id, path, label = self.samples[idx]
        try:
            wav, _sr = sf.read(path, dtype='float32')
            if wav.ndim > 1:
                wav = wav[:, 0]
        except Exception:
            wav = np.zeros(self.cut, dtype=np.float32)
        wav = pad_or_trim(wav, self.cut).astype(np.float32)
        return torch.from_numpy(wav), label, utt_id


# ============================================================
# 7.  EER
# ============================================================

def compute_eer(labels, scores):
    labels = np.array(labels, dtype=float)
    scores = np.array(scores, dtype=float)
    n_pos  = labels.sum()
    n_neg  = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    idx    = np.argsort(scores)[::-1]
    lab    = labels[idx]
    tp     = np.cumsum(lab)
    fp     = np.cumsum(1 - lab)
    fpr    = fp / n_neg
    fnr    = (n_pos - tp) / n_pos
    i      = np.nanargmin(np.abs(fpr - fnr))
    return float((fpr[i] + fnr[i]) / 2 * 100)


# ============================================================
# 8.  MAIN
# ============================================================

def main():
    pa = argparse.ArgumentParser(
        description='Evaluate XLSR-Mamba on ASVspoof5',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    pa.add_argument('--model_path',  default='model.safetensors')
    pa.add_argument('--tsv',         default='ASVspoof5.dev.track_1.tsv')
    pa.add_argument('--flac_dir',    default='flac_D')
    pa.add_argument('--batch_size',  type=int, default=4)
    pa.add_argument('--max_samples', type=int, default=None,
                    help='Limit number of samples (for quick testing)')
    pa.add_argument('--seed', type=int, default=None,
                    help='If set, --max_samples draws a uniform random subset '
                         'with this seed instead of taking the first N rows')
    pa.add_argument('--scores_out',  default='scores_dev_track1.txt')
    pa.add_argument('--device',
                    default='cuda' if torch.cuda.is_available() else 'cpu')
    args = pa.parse_args()
    device = torch.device(args.device)

    print('\n[1/4] Building model ...')
    model = Model(emb_size=144, num_encoders=12)
    nparams = sum(p.numel() for p in model.parameters()) / 1e6
    print(f'      Parameters: {nparams:.1f} M')

    print(f'\n[2/4] Loading weights from {args.model_path!r} ...')
    sd = load_file(args.model_path, device='cpu')
    miss, unexp = model.load_state_dict(sd, strict=False)
    # unexp = checkpoint tensors the architecture has no slot for; miss = model
    # params left at random init. Either means the eval is not testing the
    # trained model, so refuse to continue rather than report a bogus EER.
    if miss:  print(f'      Missing   ({len(miss)}): {miss[:3]}')
    if unexp: print(f'      Unexpected({len(unexp)}): {unexp[:3]}')
    if miss or unexp:
        raise SystemExit(
            f'ERROR: checkpoint/architecture mismatch '
            f'({len(miss)} missing, {len(unexp)} unexpected tensors). '
            f'Refusing to evaluate an incorrectly loaded model.')
    print(f'      Loaded {len(sd)}/{len(sd)} tensors OK')
    model.eval().to(device)

    print(f'\n[3/4] Loading dataset {args.tsv!r} ...')
    ds = ASVspoofDataset(args.tsv, args.flac_dir,
                         max_samples=args.max_samples, seed=args.seed)
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=False,
                    num_workers=0, drop_last=False)

    print(f'\n[4/4] Inference on {device} ...')
    scores, labels, ids = [], [], []
    p_gen = []          # softmax P(bonafide)
    with torch.no_grad():
        for wav, lbl, uid in tqdm(dl, desc='  Evaluating'):
            out = model(wav.to(device))                       # [B, 2] logits
            prob = F.softmax(out, dim=1)[:, 1]                 # P(bonafide)
            scores.extend(out[:, 1].cpu().tolist())
            p_gen.extend(prob.cpu().tolist())
            labels.extend(lbl.tolist())
            ids.extend(uid)

    out_dir = os.path.dirname(os.path.abspath(args.scores_out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.scores_out, 'w') as f:
        for uid, sc in zip(ids, scores):
            f.write(uid + ' ' + str(round(sc, 6)) + '\n')
    print(f'\n  Scores saved -> {args.scores_out}')

    # Per-utterance predictions TSV (bonafide = "genuine", spoof = "fake").
    # verdict is argmax (p_genuine >= 0.5); score_logprob = ln P(genuine).
    pred_out = os.path.splitext(args.scores_out)[0] + '_predictions.tsv'
    n_correct = 0
    with open(pred_out, 'w') as f:
        f.write('name\ttrue_label\tp_genuine\tscore_logprob\tverdict\tcorrect\n')
        for uid, lbl, p in zip(ids, labels, p_gen):
            true_lab = 'genuine' if lbl == 1 else 'fake'
            verdict  = 'genuine' if p >= 0.5 else 'fake'
            ok       = 'yes' if verdict == true_lab else 'no'
            n_correct += (verdict == true_lab)
            logp = math.log(max(p, 1e-12))
            f.write(f'{uid}\t{true_lab}\t{p:.6f}\t{logp:.4f}\t{verdict}\t{ok}\n')
    print(f'  Predictions saved -> {pred_out}  '
          f'(argmax accuracy {n_correct/len(ids)*100:.2f}%)')

    eer   = compute_eer(labels, scores)
    n_bon = int(sum(labels))
    n_sp  = len(labels) - n_bon
    sep   = '=' * 55
    print(f'\n{sep}')
    print(f'  Dataset : {os.path.basename(args.tsv)}')
    print(f'  Samples : {len(labels)}  (bonafide {n_bon}  spoof {n_sp})')
    print(f'  EER     : {eer:.2f} %')
    print(f'{sep}\n')


if __name__ == '__main__':
    main()
