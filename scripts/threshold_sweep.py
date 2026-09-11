#!/usr/bin/env python3
"""
threshold_sweep.py - Show XLSR-Mamba detection results across decision thresholds.

For each threshold: predict bonafide iff score >= thr, then report the
confusion-matrix cells and the standard rates.

Usage:
  python threshold_sweep.py
  python threshold_sweep.py --scores scores_dev_track1_sub4000.txt --n 25
"""

import argparse
import numpy as np


def load(scores_path, tsv_path):
    score = {}
    for line in open(scores_path):
        parts = line.split()
        if len(parts) == 2:
            score[parts[0]] = float(parts[1])
    label = {}
    for line in open(tsv_path):
        p = line.split()
        if len(p) >= 9:
            label[p[1]] = 1 if p[8] == 'bonafide' else 0
    ids = [i for i in score if i in label]
    s = np.array([score[i] for i in ids], dtype=float)
    y = np.array([label[i] for i in ids], dtype=int)   # 1 = bonafide, 0 = spoof
    return s, y


def eer_point(y, s):
    order = np.argsort(s)[::-1]
    lab, srt = y[order], s[order]
    n_pos, n_neg = y.sum(), len(y) - y.sum()
    tp, fp = np.cumsum(lab), np.cumsum(1 - lab)
    fpr, fnr = fp / n_neg, (n_pos - tp) / n_pos
    i = np.nanargmin(np.abs(fpr - fnr))
    return srt[i], (fpr[i] + fnr[i]) / 2 * 100


def row(y, s, thr):
    pred = (s >= thr).astype(int)
    tp = int(np.sum((y == 1) & (pred == 1)))
    fn = int(np.sum((y == 1) & (pred == 0)))
    fp = int(np.sum((y == 0) & (pred == 1)))
    tn = int(np.sum((y == 0) & (pred == 0)))
    n_bon, n_spf = tp + fn, fp + tn
    far = fp / n_spf * 100 if n_spf else float('nan')     # spoof accepted
    frr = fn / n_bon * 100 if n_bon else float('nan')     # bonafide rejected
    acc = (tp + tn) / (n_bon + n_spf) * 100
    prec = tp / (tp + fp) * 100 if (tp + fp) else float('nan')
    rec = tp / n_bon * 100 if n_bon else float('nan')
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else float('nan')
    bal_acc = (rec + (tn / n_spf * 100 if n_spf else 0)) / 2
    return dict(thr=thr, tp=tp, fn=fn, fp=fp, tn=tn, far=far, frr=frr,
               acc=acc, bal_acc=bal_acc, prec=prec, rec=rec, f1=f1)


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--scores', default='scores_dev_track1_sub4000.txt')
    pa.add_argument('--tsv', default='ASVspoof5.dev.track_1.tsv')
    pa.add_argument('--n', type=int, default=21, help='number of evenly spaced thresholds')
    pa.add_argument('--csv_out', default='threshold_sweep.csv')
    args = pa.parse_args()

    s, y = load(args.scores, args.tsv)
    n_bon, n_spf = int(y.sum()), int(len(y) - y.sum())
    print(f'{len(y)} utterances  (bonafide {n_bon}  spoof {n_spf})')

    thr_eer, eer = eer_point(y, s)

    lo, hi = np.percentile(s, 1), np.percentile(s, 99)
    grid = list(np.linspace(lo, hi, args.n))
    grid += [0.0, thr_eer]
    grid = sorted(set(round(t, 4) for t in grid))

    rows = [row(y, s, t) for t in grid]

    hdr = (f'{"thresh":>9} | {"TP":>5} {"FN":>5} {"FP":>5} {"TN":>6} | '
           f'{"FAR%":>7} {"FRR%":>7} | {"acc%":>6} {"balAcc%":>7} '
           f'{"prec%":>6} {"rec%":>6} {"F1":>6}')
    print('\n' + hdr)
    print('-' * len(hdr))
    for r in rows:
        tag = ''
        if abs(r['thr'] - round(thr_eer, 4)) < 1e-9:
            tag = '  <- EER'
        elif r['thr'] == 0.0:
            tag = '  <- score 0'
        print(f'{r["thr"]:>9.4f} | {r["tp"]:>5} {r["fn"]:>5} {r["fp"]:>5} {r["tn"]:>6} | '
              f'{r["far"]:>7.2f} {r["frr"]:>7.2f} | {r["acc"]:>6.2f} {r["bal_acc"]:>7.2f} '
              f'{r["prec"]:>6.2f} {r["rec"]:>6.2f} {r["f1"]:>6.2f}{tag}')

    print(f'\nEER = {eer:.2f}%  at threshold {thr_eer:.4f}')

    with open(args.csv_out, 'w') as f:
        f.write('threshold,TP,FN,FP,TN,FAR_pct,FRR_pct,accuracy_pct,'
                'balanced_accuracy_pct,precision_pct,recall_pct,F1\n')
        for r in rows:
            f.write(f'{r["thr"]:.4f},{r["tp"]},{r["fn"]},{r["fp"]},{r["tn"]},'
                    f'{r["far"]:.3f},{r["frr"]:.3f},{r["acc"]:.3f},{r["bal_acc"]:.3f},'
                    f'{r["prec"]:.3f},{r["rec"]:.3f},{r["f1"]:.3f}\n')
    print(f'written -> {args.csv_out}')


if __name__ == '__main__':
    main()
