#!/usr/bin/env python3
"""
plot_results.py - Visualise XLSR-Mamba detection results from a score file.

Produces a 4-panel figure:
  1. Score distributions (bonafide vs spoof) with the EER threshold
  2. ROC curve (with AUC)
  3. DET curve (with EER point)
  4. FAR / FRR / accuracy / F1 vs decision threshold

Usage:
  python plot_results.py
  python plot_results.py --scores scores_dev_track1_sub4000.txt --out results.png
"""

import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import norm


def load(scores_path, tsv_path):
    score = {}
    for line in open(scores_path):
        p = line.split()
        if len(p) == 2:
            score[p[0]] = float(p[1])
    label = {}
    for line in open(tsv_path):
        p = line.split()
        if len(p) >= 9:
            label[p[1]] = 1 if p[8] == 'bonafide' else 0
    ids = [i for i in score if i in label]
    s = np.array([score[i] for i in ids], dtype=float)
    y = np.array([label[i] for i in ids], dtype=int)   # 1 = bonafide
    return s, y


def roc_det(y, s):
    order = np.argsort(s)[::-1]
    lab = y[order]
    thr = s[order]
    n_pos, n_neg = y.sum(), len(y) - y.sum()
    tp = np.cumsum(lab)
    fp = np.cumsum(1 - lab)
    tpr = tp / n_pos
    fpr = fp / n_neg              # = FAR (spoof accepted)
    fnr = 1 - tpr                 # = FRR (bonafide rejected)
    auc = np.trapezoid(tpr, fpr)
    i = np.nanargmin(np.abs(fpr - fnr))
    eer = (fpr[i] + fnr[i]) / 2
    return fpr, tpr, fnr, thr, auc, eer, thr[i]


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--scores', default='scores_dev_track1_sub4000.txt')
    pa.add_argument('--tsv', default='ASVspoof5.dev.track_1.tsv')
    pa.add_argument('--out', default='results.png')
    args = pa.parse_args()

    s, y = load(args.scores, args.tsv)
    bona, spoof = s[y == 1], s[y == 0]
    fpr, tpr, fnr, thr, auc, eer, thr_eer = roc_det(y, s)

    C_BONA, C_SPOOF, C_ACC = '#2a9d8f', '#e76f51', '#264653'
    plt.rcParams.update({'font.size': 10, 'axes.grid': True,
                         'grid.alpha': 0.3, 'figure.facecolor': 'white'})
    fig, ax = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle(f'XLSR-Mamba  -  ASVspoof5 dev track 1  '
                 f'({len(y)} utts: {int(y.sum())} bonafide / {int(len(y)-y.sum())} spoof)',
                 fontsize=13, fontweight='bold')

    # --- 1. score distributions ---
    a = ax[0, 0]
    lo, hi = s.min(), s.max()
    bins = np.linspace(lo, hi, 60)
    a.hist(spoof, bins=bins, alpha=0.6, color=C_SPOOF, label='spoof', density=True)
    a.hist(bona, bins=bins, alpha=0.6, color=C_BONA, label='bonafide', density=True)
    a.axvline(thr_eer, color=C_ACC, ls='--', lw=1.5,
              label=f'EER threshold = {thr_eer:.2f}')
    a.axvline(0.0, color='gray', ls=':', lw=1.2, label='raw logit = 0')
    a.set_xlabel('bonafide score  (out[:, 1])')
    a.set_ylabel('density')
    a.set_title('Score distributions')
    a.legend(fontsize=8)

    # --- 2. ROC ---
    a = ax[0, 1]
    a.plot(fpr, tpr, color=C_ACC, lw=2, label=f'ROC (AUC = {auc:.4f})')
    a.plot([0, 1], [0, 1], color='gray', ls=':', lw=1)
    a.scatter([eer], [1 - eer], color=C_SPOOF, zorder=5, s=40,
              label=f'EER = {eer*100:.2f}%')
    a.set_xlabel('false-accept rate  (spoof accepted)')
    a.set_ylabel('true-accept rate  (bonafide accepted)')
    a.set_title('ROC curve')
    a.legend(fontsize=8, loc='lower right')

    # --- 3. DET (normal-deviate axes) ---
    a = ax[1, 0]
    eps = 1e-4
    f = np.clip(fpr, eps, 1 - eps)
    m = np.clip(fnr, eps, 1 - eps)
    a.plot(norm.ppf(f), norm.ppf(m), color=C_ACC, lw=2)
    a.scatter([norm.ppf(eer)], [norm.ppf(eer)], color=C_SPOOF, zorder=5, s=40,
              label=f'EER = {eer*100:.2f}%')
    ticks = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.4]
    a.set_xticks(norm.ppf(ticks)); a.set_xticklabels([f'{t*100:g}' for t in ticks])
    a.set_yticks(norm.ppf(ticks)); a.set_yticklabels([f'{t*100:g}' for t in ticks])
    a.set_xlim(norm.ppf(0.002), norm.ppf(0.5))
    a.set_ylim(norm.ppf(0.002), norm.ppf(0.5))
    a.plot(a.get_xlim(), a.get_xlim(), color='gray', ls=':', lw=1)
    a.set_xlabel('false-accept rate (%)')
    a.set_ylabel('false-reject rate (%)')
    a.set_title('DET curve')
    a.legend(fontsize=8)

    # --- 4. metrics vs threshold ---
    a = ax[1, 1]
    grid = np.linspace(np.percentile(s, 0.5), np.percentile(s, 99.5), 300)
    far = np.array([(spoof >= t).mean() for t in grid]) * 100
    frr = np.array([(bona < t).mean() for t in grid]) * 100
    acc = np.array([((bona >= t).sum() + (spoof < t).sum()) for t in grid]) / len(s) * 100
    tp = np.array([(bona >= t).sum() for t in grid], dtype=float)
    fp = np.array([(spoof >= t).sum() for t in grid], dtype=float)
    fn = np.array([(bona < t).sum() for t in grid], dtype=float)
    f1 = np.where((2*tp + fp + fn) > 0, 2*tp / (2*tp + fp + fn), 0) * 100
    a.plot(grid, far, color=C_SPOOF, lw=1.8, label='FAR % (spoof accepted)')
    a.plot(grid, frr, color=C_BONA, lw=1.8, label='FRR % (bonafide rejected)')
    a.plot(grid, acc, color=C_ACC, lw=1.8, label='accuracy %')
    a.plot(grid, f1, color='#e9c46a', lw=1.8, label='F1 (bonafide)')
    a.axvline(thr_eer, color='gray', ls='--', lw=1.2)
    a.annotate(f'EER thr {thr_eer:.2f}', xy=(thr_eer, 50),
               xytext=(6, 0), textcoords='offset points', fontsize=8, rotation=90,
               va='center')
    a.set_xlabel('decision threshold')
    a.set_ylabel('%')
    a.set_ylim(-2, 102)
    a.set_title('Error rates & metrics vs threshold')
    a.legend(fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(args.out, dpi=130)
    print(f'AUC = {auc:.4f}   EER = {eer*100:.2f}%   EER threshold = {thr_eer:.4f}')
    print(f'figure -> {args.out}')


if __name__ == '__main__':
    main()
