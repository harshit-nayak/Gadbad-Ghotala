#!/usr/bin/env python3
"""
confusion_all_languages.py - Confusion matrices for a checkpoint across every
language currently sitting in indic_df/manifest.tsv (whether or not that
language was used in training).

For hi/bn/ta (the training languages) only the held-out 'test' split is used.
For every other language (ml, gu, ... - whatever the corpus currently has),
ALL of its clips are used, since neither the plain nor the agnostic checkpoint
was ever trained on them - every clip is equally "held out."

The decision threshold is fixed at the EER point of the hi/bn/ta test set (the
in-domain, deployment-realistic operating point) and applied unchanged to
every language, including the unseen ones - exactly what happens if you ship
one threshold and point the model at new traffic.

Runs the FULL model (backbone + head) on raw audio, so it works uniformly
regardless of whether a language's features were ever cached.
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
TRAIN_LANGS = {'hi', 'bn', 'ta'}   # languages this checkpoint actually trained on


def load_manifest():
    with open(MANIFEST, encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def select_eval_rows(all_rows):
    """Test split for trained languages; every clip for languages never trained on."""
    langs = sorted(set(r['lang'] for r in all_rows))
    out = {}
    for lg in langs:
        lg_rows = [r for r in all_rows if r['lang'] == lg]
        if lg in TRAIN_LANGS:
            lg_rows = [r for r in lg_rows if r['split'] == 'test']
        out[lg] = lg_rows
    return out


def score(model, rows, device, batch_size=32):
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


def report(title, y, s, thr):
    tp, fn, fp, tn = confusion(y, s, thr)
    n_r, n_f, total = tp + fn, fp + tn, len(y)
    acc = (tp + tn) / total * 100 if total else float('nan')
    prec = tp / (tp + fp) * 100 if (tp + fp) else float('nan')
    rec = tp / n_r * 100 if n_r else float('nan')
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else float('nan')
    own_eer = compute_eer(y, s) if 0 < y.sum() < len(y) else float('nan')
    print(f'\n{title}  (n={total}, real={n_r}, fake={n_f})')
    print('                    pred. real   pred. fake')
    print(f'  actual real     {tp:>10d}   {fn:>10d}')
    print(f'  actual fake     {fp:>10d}   {tn:>10d}')
    print(f'  accuracy {acc:.2f}%  precision {prec:.2f}%  recall {rec:.2f}%  F1 {f1:.2f}  '
          f'own-threshold EER {own_eer:.2f}%')
    return dict(tp=tp, fn=fn, fp=fp, tn=tn, acc=acc, prec=prec, rec=rec, f1=f1, own_eer=own_eer)


def main():
    global TRAIN_LANGS
    pa = argparse.ArgumentParser()
    pa.add_argument('--model_path', default='model_indic_ft_agnostic.safetensors')
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    pa.add_argument('--csv_out', default='results_indic/confusion_all_languages.csv')
    pa.add_argument('--train_langs', default='hi,bn,ta',
                    help='comma-separated languages this checkpoint was actually trained on '
                         '(only their test split is used; every other language uses all rows)')
    args = pa.parse_args()
    device = torch.device(args.device)
    TRAIN_LANGS = set(args.train_langs.split(','))

    model = Model(emb_size=144, num_encoders=12)
    sd = load_file(args.model_path, device='cpu')
    miss, unexp = model.load_state_dict(sd, strict=False)
    if miss or unexp:
        raise SystemExit(f'{args.model_path}: tensor mismatch ({len(miss)} missing, {len(unexp)} unexpected)')
    model.eval().to(device)
    print(f'model: {args.model_path}')

    all_rows = load_manifest()
    by_lang = select_eval_rows(all_rows)
    langs = sorted(by_lang)
    print('languages found in corpus:', langs)
    print('trained on:', sorted(TRAIN_LANGS & set(langs)), ' | never trained on:', sorted(set(langs) - TRAIN_LANGS))

    # score every language once
    scores_by_lang, labels_by_lang = {}, {}
    for lg in langs:
        rows = by_lang[lg]
        print(f'  scoring {lg}: {len(rows)} clips ...', flush=True)
        s = score(model, rows, device)
        y = np.array([int(r['label']) for r in rows])
        scores_by_lang[lg], labels_by_lang[lg] = s, y

    # fixed operating threshold = EER point of the trained-language (hi/bn/ta) test set
    train_mask_langs = [lg for lg in langs if lg in TRAIN_LANGS]
    y_train = np.concatenate([labels_by_lang[lg] for lg in train_mask_langs])
    s_train = np.concatenate([scores_by_lang[lg] for lg in train_mask_langs])
    thr, in_domain_eer = eer_threshold(y_train, s_train)
    print(f'\nFixed operating threshold = {thr:.4f}  (EER point on hi/bn/ta test set, in-domain EER {in_domain_eer:.2f}%)')

    rows_out = []
    y_all = np.concatenate([labels_by_lang[lg] for lg in langs])
    s_all = np.concatenate([scores_by_lang[lg] for lg in langs])
    r = report(f'=== ALL LANGUAGES COMBINED ({"+".join(langs)}) ===', y_all, s_all, thr)
    rows_out.append(('overall', 'all', r))

    for lg in langs:
        tag = 'trained' if lg in TRAIN_LANGS else 'UNSEEN'
        r = report(f'=== {lg}  [{tag}] ===', labels_by_lang[lg], scores_by_lang[lg], thr)
        rows_out.append(('lang', lg, r))

    os.makedirs(os.path.dirname(args.csv_out), exist_ok=True)
    with open(args.csv_out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['group', 'lang', 'trained_on', 'n', 'TP', 'FN', 'FP', 'TN',
                    'accuracy_pct', 'precision_pct', 'recall_pct', 'F1', 'own_threshold_eer_pct'])
        for group, lg, r in rows_out:
            trained = '' if group == 'overall' else ('yes' if lg in TRAIN_LANGS else 'no')
            n = r['tp'] + r['fn'] + r['fp'] + r['tn']
            w.writerow([group, lg, trained, n, r['tp'], r['fn'], r['fp'], r['tn'],
                       f"{r['acc']:.2f}", f"{r['prec']:.2f}", f"{r['rec']:.2f}", f"{r['f1']:.2f}",
                       f"{r['own_eer']:.2f}"])
    print(f'\n-> {args.csv_out}')


if __name__ == '__main__':
    main()
