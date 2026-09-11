#!/usr/bin/env python3
"""
confusion_matrix.py - Build confusion matrices from an XLSR-Mamba score file.

Score file format (one line per utterance):  <utt_id> <score>
Higher score => more "bonafide".  Labels are read from the ASVspoof5 TSV.

Usage:
  python confusion_matrix.py
  python confusion_matrix.py --scores scores_dev_track1_sub4000.txt --tsv ASVspoof5.dev.track_1.tsv
"""

import argparse
import numpy as np


def load(scores_path, tsv_path):
    score = {}
    for line in open(scores_path):
        parts = line.split()
        if len(parts) != 2:
            continue
        score[parts[0]] = float(parts[1])
    label = {}
    for line in open(tsv_path):
        p = line.split()
        if len(p) >= 9:
            label[p[1]] = 1 if p[8] == 'bonafide' else 0
    ids = [i for i in score if i in label]
    s = np.array([score[i] for i in ids], dtype=float)
    y = np.array([label[i] for i in ids], dtype=int)   # 1 = bonafide, 0 = spoof
    return ids, s, y


def eer_threshold(y, s):
    """Threshold where false-accept rate == false-reject rate."""
    order = np.argsort(s)[::-1]
    lab = y[order]
    srt = s[order]
    n_pos = y.sum()
    n_neg = len(y) - n_pos
    tp = np.cumsum(lab)
    fp = np.cumsum(1 - lab)
    fpr = fp / n_neg                 # spoof accepted as bonafide
    fnr = (n_pos - tp) / n_pos       # bonafide rejected as spoof
    i = np.nanargmin(np.abs(fpr - fnr))
    eer = (fpr[i] + fnr[i]) / 2 * 100
    return srt[i], eer


def confusion(y, s, thr):
    """Predicted bonafide iff score >= thr. Rows = actual, cols = predicted."""
    pred = (s >= thr).astype(int)
    tp = int(np.sum((y == 1) & (pred == 1)))   # bonafide -> bonafide
    fn = int(np.sum((y == 1) & (pred == 0)))   # bonafide -> spoof
    fp = int(np.sum((y == 0) & (pred == 1)))   # spoof    -> bonafide
    tn = int(np.sum((y == 0) & (pred == 0)))   # spoof    -> spoof
    return tp, fn, fp, tn


def show(title, thr, y, s):
    tp, fn, fp, tn = confusion(y, s, thr)
    n_bon = tp + fn
    n_spf = fp + tn
    total = n_bon + n_spf
    acc = (tp + tn) / total * 100
    far = fp / n_spf * 100 if n_spf else float('nan')   # spoof false-accept rate
    frr = fn / n_bon * 100 if n_bon else float('nan')   # bonafide false-reject rate
    prec = tp / (tp + fp) * 100 if (tp + fp) else float('nan')
    rec = tp / n_bon * 100 if n_bon else float('nan')
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else float('nan')

    print(f'\n{title}')
    print(f'  threshold = {thr:.6f}')
    print('                          predicted')
    print('                    bonafide      spoof        total')
    print(f'  actual bonafide  {tp:>8d}   {fn:>10d}   {n_bon:>10d}')
    print(f'  actual spoof     {fp:>8d}   {tn:>10d}   {n_spf:>10d}')
    print(f'  total            {tp + fp:>8d}   {fn + tn:>10d}   {total:>10d}')
    print(f'  accuracy {acc:.2f}%   precision {prec:.2f}%   recall {rec:.2f}%   F1 {f1:.2f}')
    print(f'  spoof false-accept rate {far:.2f}%   bonafide false-reject rate {frr:.2f}%')


def main():
    pa = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument('--scores', default='scores_dev_track1_sub4000.txt')
    pa.add_argument('--tsv', default='ASVspoof5.dev.track_1.tsv')
    pa.add_argument('--threshold', type=float, default=None,
                    help='Fixed decision threshold (default: also show EER point and 0.0)')
    pa.add_argument('--csv_out', default='confusion_matrix.csv')
    args = pa.parse_args()

    ids, s, y = load(args.scores, args.tsv)
    print(f'Loaded {len(ids)} scored utterances  '
          f'(bonafide {int(y.sum())}  spoof {int(len(y) - y.sum())})')

    thr_eer, eer = eer_threshold(y, s)
    print(f'EER = {eer:.2f}%')

    show('=== Confusion matrix @ EER-equal-error threshold ===', thr_eer, y, s)
    show('=== Confusion matrix @ threshold 0.0 ===', 0.0, y, s)
    if args.threshold is not None:
        show(f'=== Confusion matrix @ threshold {args.threshold} ===', args.threshold, y, s)

    tp, fn, fp, tn = confusion(y, s, thr_eer)
    with open(args.csv_out, 'w') as f:
        f.write('actual\\predicted,bonafide,spoof\n')
        f.write(f'bonafide,{tp},{fn}\n')
        f.write(f'spoof,{fp},{tn}\n')
    print(f'\nEER-threshold matrix written -> {args.csv_out}')


if __name__ == '__main__':
    main()
