#!/usr/bin/env python3
"""
probe_mms_vs_xlsr.py - Quick sanity check: does swapping the frozen backbone
from XLSR (currently used) to MMS-300m give better real/fake separability on
Malayalam, the language where the current pipeline fails hardest (65.37% acc,
31.64% EER)?

Method: pull a balanced sample of Malayalam real+fake clips, extract mean-
pooled embeddings from both backbones (no head, no training), and score
linear-probe separability with 5-fold cross-validated logistic regression on
each. This isolates "does the backbone's feature space separate real/fake"
from "can the trained head classify it" - if MMS's embeddings are much more
linearly separable, that's strong evidence a full backbone swap is worth the
~2-2.5hr cost; if not, skip it.
"""
import csv
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import SSLModel, pad_or_trim          # noqa: E402
from safetensors.torch import load_file                    # noqa: E402

MANIFEST = r'C:\Users\ATHARV\SIH_data\indic_df\manifest.tsv'
CUT = 66800
N_PER_CLASS = 150
SEED = 0


def load_ml_clips():
    with open(MANIFEST, encoding='utf-8') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    ml = [r for r in rows if r['lang'] == 'ml']
    rng = np.random.RandomState(SEED)
    by_label = {'0': [], '1': []}
    for r in ml:
        by_label[r['label']].append(r)
    for k in by_label:
        rng.shuffle(by_label[k])
        by_label[k] = by_label[k][:N_PER_CLASS]
    kept = by_label['0'] + by_label['1']
    y = np.array([int(r['label']) for r in kept])
    return kept, y


def load_wavs(rows):
    wavs = []
    for r in rows:
        try:
            w, _ = sf.read(r['path'], dtype='float32')
            if w.ndim > 1:
                w = w[:, 0]
        except Exception as e:
            print('read fail', r['path'], e)
            w = np.zeros(CUT, dtype=np.float32)
        wavs.append(pad_or_trim(w, CUT).astype(np.float32))
    return np.stack(wavs)


@torch.no_grad()
def embed_xlsr(wavs, device, batch_size=16):
    ssl = SSLModel().to(device).eval()
    sd = load_file(os.path.join(_HERE, 'model_indic_ft_agnostic.safetensors'), device='cpu')
    ssl_sd = {k[len('ssl_model.'):]: v for k, v in sd.items() if k.startswith('ssl_model.')}
    missing, unexpected = ssl.load_state_dict(ssl_sd, strict=False)
    print(f'  xlsr backbone load: missing={len(missing)} unexpected={len(unexpected)}')
    embs = []
    for i in range(0, len(wavs), batch_size):
        x = torch.from_numpy(wavs[i:i + batch_size]).to(device)
        feat, _ = ssl.extract_feat(x)
        embs.append(feat.mean(dim=1).cpu().numpy())
    del ssl
    torch.cuda.empty_cache()
    return np.concatenate(embs, axis=0)


@torch.no_grad()
def embed_mms(wavs, device, batch_size=16):
    from transformers import Wav2Vec2Model
    model = Wav2Vec2Model.from_pretrained('facebook/mms-300m').to(device).eval()
    embs = []
    for i in range(0, len(wavs), batch_size):
        x = torch.from_numpy(wavs[i:i + batch_size]).to(device)
        out = model(x).last_hidden_state
        embs.append(out.mean(dim=1).cpu().numpy())
    del model
    torch.cuda.empty_cache()
    return np.concatenate(embs, axis=0)


def probe_score(X, y, name):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    Xs = StandardScaler().fit_transform(X)
    clf = LogisticRegression(max_iter=2000, C=1.0)
    scores = cross_val_score(clf, Xs, y, cv=5, scoring='accuracy')
    print(f'{name}: linear-probe 5-fold CV accuracy = {scores.mean()*100:.2f}% (+/- {scores.std()*100:.2f}), '
          f'folds={np.round(scores*100,2)}')
    return scores.mean()


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('device:', device)

    rows, y = load_ml_clips()
    print(f'Malayalam probe set: {len(rows)} clips (real={np.sum(y==0)}, fake={np.sum(y==1)})')
    t0 = time.time()
    wavs = load_wavs(rows)
    print(f'audio loaded in {time.time()-t0:.1f}s')

    t0 = time.time()
    print('\nExtracting XLSR (current backbone) embeddings...')
    X_xlsr = embed_xlsr(wavs, device)
    print(f'  done in {time.time()-t0:.1f}s, shape={X_xlsr.shape}')

    t0 = time.time()
    print('\nExtracting MMS-300m embeddings...')
    X_mms = embed_mms(wavs, device)
    print(f'  done in {time.time()-t0:.1f}s, shape={X_mms.shape}')

    print()
    acc_xlsr = probe_score(X_xlsr, y, 'XLSR  (current)')
    acc_mms = probe_score(X_mms, y, 'MMS-300m')

    print(f'\n=== VERDICT ===')
    print(f'XLSR linear-probe accuracy:     {acc_xlsr*100:.2f}%')
    print(f'MMS-300m linear-probe accuracy: {acc_mms*100:.2f}%')
    delta = (acc_mms - acc_xlsr) * 100
    print(f'delta: {delta:+.2f} points')
    if delta > 8:
        print('-> MMS embeddings are meaningfully more separable. Full backbone swap looks worth it.')
    elif delta > 2:
        print('-> MMS is somewhat better but not dramatically. Marginal case.')
    else:
        print('-> No meaningful separability gain. Backbone swap likely NOT worth the ~2-2.5hr cost.')


if __name__ == '__main__':
    main()
