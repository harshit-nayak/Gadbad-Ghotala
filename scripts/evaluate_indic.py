#!/usr/bin/env python3
"""
evaluate_indic.py - Score a model on the Indic deepfake test split and report
EER overall / per-language / per-codec (clean vs whatsapp-compressed).

Uses the cached test features (indic_df/feat/test.*). Pass --model_path to pick
the checkpoint (base model.safetensors or fine-tuned model_indic_ft.safetensors).
"""

import argparse, csv, os, sys
import numpy as np
import torch
from safetensors.torch import load_file

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import Model, compute_eer          # noqa: E402

FEAT = os.path.join(os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df'), 'feat')
TFRAMES, FDIM = 208, 144


def load_split(split):
    meta = list(csv.DictReader(open(os.path.join(FEAT, f'{split}.tsv'), encoding='utf-8'),
                               delimiter='\t'))
    mm = np.memmap(os.path.join(FEAT, f'{split}.dat'), dtype='float16', mode='r',
                   shape=(len(meta), TFRAMES, FDIM))
    return meta, mm


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--model_path', default='model_indic_ft.safetensors')
    pa.add_argument('--split', default='test')
    pa.add_argument('--batch_size', type=int, default=256)
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    pa.add_argument('--out', default='results_indic/eval_%s.tsv')
    args = pa.parse_args()
    device = torch.device(args.device)

    model = Model(emb_size=144, num_encoders=12)
    model.load_state_dict(load_file(args.model_path, device='cpu'), strict=False)
    model.eval().to(device)

    meta, mm = load_split(args.split)
    N = len(meta)
    sc = np.zeros(N)
    with torch.no_grad():
        for i in range(0, N, args.batch_size):
            h = torch.from_numpy(np.asarray(mm[i:i + args.batch_size], dtype=np.float32)).to(device)
            sc[i:i + args.batch_size] = model.conformer(h)[:, 1].cpu().numpy()

    lab   = np.array([int(m['label']) for m in meta])
    lang  = np.array([m['lang'] for m in meta])
    codec = np.array([m['codec'] for m in meta])
    gm    = np.array([m['genmodel'] for m in meta])

    tag = os.path.splitext(os.path.basename(args.model_path))[0]
    print(f'\n=== {tag}  on Indic {args.split}  ({N} clips) ===')
    rows = [('overall', '', compute_eer(lab, sc), N)]
    print(f'  overall EER         {rows[0][2]:.2f}%   (n={N})')
    for name, arr in [('lang', lang), ('codec', codec)]:
        for v in sorted(set(arr)):
            m = arr == v
            if 0 < lab[m].sum() < m.sum():
                e = compute_eer(lab[m], sc[m])
                rows.append((name, v, e, int(m.sum()))); print(f'  {name:5s} {v:10s}  {e:.2f}%   (n={int(m.sum())})')
    # cross: lang x codec
    for lg in sorted(set(lang)):
        for cd in sorted(set(codec)):
            m = (lang == lg) & (codec == cd)
            if 0 < lab[m].sum() < m.sum():
                e = compute_eer(lab[m], sc[m])
                rows.append(('lang_codec', f'{lg}/{cd}', e, int(m.sum())))
                print(f'  {lg}/{cd:9s}       {e:.2f}%   (n={int(m.sum())})')

    op = args.out % args.split if '%s' in args.out else args.out
    os.makedirs(os.path.dirname(op), exist_ok=True)
    with open(op, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['group', 'value', 'eer_pct', 'n'])
        w.writerows(rows)
    print(f'\n  -> {op}')


if __name__ == '__main__':
    main()
