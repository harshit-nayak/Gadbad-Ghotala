#!/usr/bin/env python3
"""
evaluate_cross_lingual.py - The actual test of "language-agnostic": score a
checkpoint on languages it never trained on.

model_indic_ft.safetensors and model_indic_ft_agnostic.safetensors were both
trained on Hindi/Bengali/Tamil only. This scores each of them on the Malayalam
and Gujarati clips already sitting in indic_df/ (collected during an earlier,
abandoned language-expansion attempt, never used for training either
checkpoint) - a genuine held-out-language test, not just a held-out-speaker one.

Runs the FULL model (backbone + head) on raw audio, since these languages were
never feature-cached.
"""

import argparse, csv, os, sys
import numpy as np
import soundfile as sf
import torch
from safetensors.torch import load_file

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import Model, pad_or_trim, compute_eer          # noqa: E402

MANIFEST = os.path.join(os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df'),
                        'manifest.tsv')
CUT = 66800


def load_clips(langs, max_per_lang=None, codec=None):
    rows = []
    with open(MANIFEST, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if r['lang'] in langs and (codec is None or r['codec'] == codec):
                rows.append(r)
    if max_per_lang:
        # cap per (lang, label), not per lang alone - manifest rows are grouped by
        # class as they're streamed in, so an unlabeled per-lang cap can silently
        # grab all-bonafide or all-spoof and leave EER undefined.
        by_key = {}
        kept = []
        for r in rows:
            key = (r['lang'], r['label'])
            by_key.setdefault(key, 0)
            if by_key[key] < max_per_lang:
                kept.append(r); by_key[key] += 1
        rows = kept
    return rows


def score_model(model_path, rows, device, batch_size=32):
    model = Model(emb_size=144, num_encoders=12)
    sd = load_file(model_path, device='cpu')
    miss, unexp = model.load_state_dict(sd, strict=False)
    if miss or unexp:
        raise SystemExit(f'{model_path}: tensor mismatch ({len(miss)} missing, {len(unexp)} unexpected)')
    model.eval().to(device)

    scores = np.zeros(len(rows))
    with torch.no_grad():
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            wavs = []
            for r in batch:
                try:
                    w, _ = sf.read(r['path'], dtype='float32')
                    if w.ndim > 1:
                        w = w[:, 0]
                except Exception:
                    w = np.zeros(CUT, dtype=np.float32)
                wavs.append(pad_or_trim(w, CUT).astype(np.float32))
            x = torch.from_numpy(np.stack(wavs)).to(device)
            out = model(x)
            scores[i:i + len(batch)] = out[:, 1].cpu().numpy()
    return scores


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--langs', default='ml,gu', help='comma-separated language codes to test on')
    pa.add_argument('--models', default='model_indic_ft.safetensors,model_indic_ft_agnostic.safetensors')
    pa.add_argument('--max_per_lang', type=int, default=1500)
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    pa.add_argument('--out', default='results_indic/cross_lingual_eval.csv')
    args = pa.parse_args()
    device = torch.device(args.device)

    langs = args.langs.split(',')
    rows = load_clips(langs, max_per_lang=args.max_per_lang)
    labels = np.array([int(r['label']) for r in rows])
    lang_arr = np.array([r['lang'] for r in rows])
    codec_arr = np.array([r['codec'] for r in rows])
    print(f'held-out-language test set: {len(rows)} clips, langs={dict(zip(*np.unique(lang_arr, return_counts=True)))}, '
          f'bonafide={int(labels.sum())} spoof={int((1-labels).sum())}')

    results = []
    for model_path in args.models.split(','):
        model_path = model_path.strip()
        if not os.path.exists(model_path):
            print(f'  [skip] {model_path} not found'); continue
        print(f'\n=== {model_path} ===')
        scores = score_model(model_path, rows, device)
        overall = compute_eer(labels, scores)
        print(f'  overall EER (never trained on {langs}): {overall:.2f}%')
        row = {'model': model_path, 'group': 'overall', 'value': '+'.join(langs), 'eer': overall, 'n': len(rows)}
        results.append(row)
        for lg in sorted(set(lang_arr)):
            m = lang_arr == lg
            if 0 < labels[m].sum() < m.sum():
                e = compute_eer(labels[m], scores[m])
                print(f'  {lg}: {e:.2f}%  (n={int(m.sum())})')
                results.append({'model': model_path, 'group': 'lang', 'value': lg, 'eer': e, 'n': int(m.sum())})
        for cd in sorted(set(codec_arr)):
            m = codec_arr == cd
            if 0 < labels[m].sum() < m.sum():
                e = compute_eer(labels[m], scores[m])
                print(f'  codec={cd}: {e:.2f}%  (n={int(m.sum())})')
                results.append({'model': model_path, 'group': 'codec', 'value': cd, 'eer': e, 'n': int(m.sum())})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['model', 'group', 'value', 'eer', 'n'])
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f'\n-> {args.out}')

    if len(results) >= 2:
        by_model_overall = {r['model']: r['eer'] for r in results if r['group'] == 'overall'}
        if len(by_model_overall) == 2:
            (a, ea), (b, eb) = list(by_model_overall.items())
            better = a if ea < eb else b
            print(f'\nOn languages neither model trained on: {a}={ea:.2f}% vs {b}={eb:.2f}% '
                  f'-> {better} generalizes better')


if __name__ == '__main__':
    main()
