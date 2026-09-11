#!/usr/bin/env python3
"""
confusion_indic.py - Confusion matrix for a fine-tuned model on the Indic
deepfake test split (cached features), at the EER-equal-error threshold.

Runs on CPU by default (inference through the 1.79M-param head only, on
already-cached features, so it's cheap and won't contend with a GPU training
job running at the same time).
"""

import argparse, csv, os, sys
import numpy as np
import torch
from safetensors import safe_open

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import MixerModel, MambaConfig, compute_eer          # noqa: E402

FEAT = os.path.join(os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df'), 'feat')
TFRAMES, FDIM = 208, 144


def eer_threshold(y, s):
    order = np.argsort(s)[::-1]
    lab, srt = y[order], s[order]
    n_pos, n_neg = y.sum(), len(y) - y.sum()
    tp, fp = np.cumsum(lab), np.cumsum(1 - lab)
    fpr, fnr = fp / n_neg, (n_pos - tp) / n_pos
    i = np.nanargmin(np.abs(fpr - fnr))
    return srt[i], (fpr[i] + fnr[i]) / 2 * 100


def confusion(y, s, thr):
    pred = (s >= thr).astype(int)
    tp = int(np.sum((y == 1) & (pred == 1)))
    fn = int(np.sum((y == 1) & (pred == 0)))
    fp = int(np.sum((y == 0) & (pred == 1)))
    tn = int(np.sum((y == 0) & (pred == 0)))
    return tp, fn, fp, tn


def show(title, y, s, thr):
    tp, fn, fp, tn = confusion(y, s, thr)
    n_r, n_f = tp + fn, fp + tn
    total = n_r + n_f
    acc = (tp + tn) / total * 100 if total else float('nan')
    prec = tp / (tp + fp) * 100 if (tp + fp) else float('nan')
    rec = tp / n_r * 100 if n_r else float('nan')
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else float('nan')
    print(f'\n{title}  (n={total}, threshold={thr:.4f})')
    print('                       predicted')
    print('                   real        fake       total')
    print(f'  actual real   {tp:>8d}   {fn:>9d}   {n_r:>9d}')
    print(f'  actual fake   {fp:>8d}   {tn:>9d}   {n_f:>9d}')
    print(f'  total         {tp+fp:>8d}   {fn+tn:>9d}   {total:>9d}')
    print(f'  accuracy {acc:.2f}%   precision {prec:.2f}%   recall {rec:.2f}%   F1 {f1:.2f}')
    return dict(tp=tp, fn=fn, fp=fp, tn=tn, acc=acc, prec=prec, rec=rec, f1=f1)


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--model_path', default='model_indic_ft.safetensors')
    pa.add_argument('--split', default='test')
    pa.add_argument('--device', default='cpu')
    pa.add_argument('--csv_out', default='results_indic/confusion_indic.csv')
    args = pa.parse_args()
    device = torch.device(args.device)

    # Only the conformer head is needed for inference on cached features - skip
    # constructing/loading the 317M-param frozen XLSR backbone entirely (avoids
    # the memory pressure of a second full model load while training runs).
    cfg = MambaConfig(d_model=144, n_layer=12 // 2)
    conformer = MixerModel(d_model=cfg.d_model, n_layer=cfg.n_layer, ssm_cfg=cfg.ssm_cfg,
                           rms_norm=cfg.rms_norm, residual_in_fp32=cfg.residual_in_fp32,
                           fused_add_norm=cfg.fused_add_norm)
    sd = {}
    with safe_open(args.model_path, framework='pt', device='cpu') as f:
        for k in f.keys():
            if k.startswith('conformer.'):
                sd[k[len('conformer.'):]] = f.get_tensor(k)
    conformer.load_state_dict(sd, strict=True)
    conformer.eval().to(device)

    meta = list(csv.DictReader(open(os.path.join(FEAT, f'{args.split}.tsv'), encoding='utf-8'),
                               delimiter='\t'))
    N = len(meta)
    mm = np.memmap(os.path.join(FEAT, f'{args.split}.dat'), dtype='float16', mode='r',
                   shape=(N, TFRAMES, FDIM))

    sc = np.zeros(N)
    bs = 256
    with torch.no_grad():
        for i in range(0, N, bs):
            h = torch.from_numpy(np.asarray(mm[i:i + bs], dtype=np.float32)).to(device)
            sc[i:i + bs] = conformer(h)[:, 1].cpu().numpy()

    lab   = np.array([int(m['label']) for m in meta])
    lang  = np.array([m['lang'] for m in meta])
    codec = np.array([m['codec'] for m in meta])

    thr, eer = eer_threshold(lab, sc)
    print(f'Model: {args.model_path}   split: {args.split}   n={N}')
    print(f'EER = {eer:.2f}%  at threshold {thr:.4f}')

    rows = []
    r = show('=== OVERALL (real=bonafide/IndicVoices-R, fake=spoof/IndicSynth) ===', lab, sc, thr)
    rows.append(('overall', 'all', r))
    for lg in sorted(set(lang)):
        m = lang == lg
        r = show(f'=== language: {lg} ===', lab[m], sc[m], thr)
        rows.append(('lang', lg, r))
    for cd in sorted(set(codec)):
        m = codec == cd
        r = show(f'=== codec: {cd} ===', lab[m], sc[m], thr)
        rows.append(('codec', cd, r))

    os.makedirs(os.path.dirname(args.csv_out), exist_ok=True)
    with open(args.csv_out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['group', 'value', 'TP', 'FN', 'FP', 'TN', 'accuracy_pct',
                    'precision_pct', 'recall_pct', 'F1'])
        for group, value, r in rows:
            w.writerow([group, value, r['tp'], r['fn'], r['fp'], r['tn'],
                       f"{r['acc']:.2f}", f"{r['prec']:.2f}", f"{r['rec']:.2f}", f"{r['f1']:.2f}"])
    print(f'\n-> {args.csv_out}')


if __name__ == '__main__':
    main()
