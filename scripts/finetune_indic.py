#!/usr/bin/env python3
"""
finetune_indic.py - Fine-tune the XLSR-Mamba conformer head on the Indic
audio-deepfake corpus (real = IndicVoices-R, fake = IndicSynth), with the
WhatsApp-Opus-compressed clips baked into the manifest.

Backbone + LL + first_bn are frozen (see cache_features.py); only
model.conformer (the dual-column Mamba head + classifier) is trained, on the
memmapped features.

Output:
  model_indic_ft.safetensors        best full model state dict
  results_indic/finetune_log.tsv    per-epoch train loss + dev EER (overall/lang/codec)
"""

import argparse, csv, math, os, sys, time
import numpy as np
import torch
import torch.nn as nn
from safetensors.torch import load_file, save_file

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import Model, compute_eer          # noqa: E402

OUT = os.path.join(os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df'), 'feat')
RES = os.path.join(_HERE, 'results_indic')
TFRAMES, FDIM = 208, 144


class FeatSet(torch.utils.data.Dataset):
    def __init__(self, split, aug=False, crop=None):
        self.meta = list(csv.DictReader(
            open(os.path.join(OUT, f'{split}.tsv'), encoding='utf-8'), delimiter='\t'))
        self.N = len(self.meta)
        self.mm = np.memmap(os.path.join(OUT, f'{split}.dat'), dtype='float16',
                            mode='r', shape=(self.N, TFRAMES, FDIM))
        self.aug = aug
        # The Mamba selective-scan backward pass is a sequential Python loop over
        # timesteps, so its cost scales ~linearly with sequence length. Training
        # on a shorter random crop of the cached features cuts that cost a lot;
        # eval still uses the full TFRAMES (crop=None).
        self.crop = crop

    def __len__(self):
        return self.N

    def __getitem__(self, i):
        h = np.asarray(self.mm[i], dtype=np.float32)
        if self.crop and self.crop < TFRAMES:
            t0 = np.random.randint(0, TFRAMES - self.crop + 1)
            h = h[t0:t0 + self.crop]
        if self.aug:
            n = h.shape[0]
            if np.random.rand() < 0.5 and n > 20:            # frame mask
                t0 = np.random.randint(0, n - 20)
                h[t0:t0 + np.random.randint(5, 20)] = 0.0
            if np.random.rand() < 0.5:                       # feature noise
                h = h + np.random.randn(*h.shape).astype(np.float32) * 0.05
        m = self.meta[i]
        return torch.from_numpy(h), int(m['label']), m['lang'], m['codec']


def evaluate(model, dl, device):
    model.conformer.eval()
    sc, lab, lang, codec = [], [], [], []
    with torch.no_grad():
        for h, y, lg, cd in dl:
            out = model.conformer(h.to(device))
            sc.extend(out[:, 1].cpu().tolist())
            lab.extend(y.tolist()); lang.extend(lg); codec.extend(cd)
    sc, lab = np.array(sc), np.array(lab)
    res = {'overall': compute_eer(lab, sc)}
    for key, arr in [('lang', np.array(lang)), ('codec', np.array(codec))]:
        for v in sorted(set(arr)):
            m = arr == v
            if 0 < lab[m].sum() < m.sum():
                res[f'{key}:{v}'] = compute_eer(lab[m], sc[m])
    return res


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--epochs', type=int, default=40)
    pa.add_argument('--batch_size', type=int, default=64)
    pa.add_argument('--lr', type=float, default=3e-4)
    pa.add_argument('--wd', type=float, default=1e-4)
    pa.add_argument('--patience', type=int, default=8)
    pa.add_argument('--train_crop', type=int, default=None,
                    help='random-crop cached train features to this many frames '
                         '(speeds up the sequential Mamba-scan backward pass)')
    pa.add_argument('--model_path', default='model.safetensors')
    pa.add_argument('--out', default='model_indic_ft.safetensors')
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    args = pa.parse_args()
    device = torch.device(args.device)
    os.makedirs(RES, exist_ok=True)

    model = Model(emb_size=144, num_encoders=12)
    base_sd = load_file(args.model_path, device='cpu')
    model.load_state_dict(base_sd, strict=False)
    model.to(device)
    for p in model.parameters():
        p.requires_grad_(False)
    for p in model.conformer.parameters():
        p.requires_grad_(True)
    ntrain = sum(p.numel() for p in model.conformer.parameters()) / 1e6
    print(f'training conformer head: {ntrain:.2f} M params')

    tr = torch.utils.data.DataLoader(FeatSet('train', aug=True, crop=args.train_crop),
                                     batch_size=args.batch_size,
                                     shuffle=True, num_workers=0, drop_last=True)
    dv = torch.utils.data.DataLoader(FeatSet('dev'), batch_size=256, num_workers=0)
    print(f'train {len(tr.dataset)}  dev {len(dv.dataset)}')

    opt = torch.optim.AdamW(model.conformer.parameters(), lr=args.lr, weight_decay=args.wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    lossf = nn.CrossEntropyLoss()

    logp = open(os.path.join(RES, 'finetune_log.tsv'), 'w', encoding='utf-8')
    logp.write('epoch\ttrain_loss\tdev_eer_overall\tdetail\n')
    best, best_ep, bad = 1e9, -1, 0

    nbatches = len(tr)
    for ep in range(1, args.epochs + 1):
        model.conformer.train()
        t0, tot, nb = time.time(), 0.0, 0
        for h, y, _, _ in tr:
            h, y = h.to(device), y.to(device)
            out = model.conformer(h)
            loss = lossf(out, y)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.conformer.parameters(), 5.0)
            opt.step()
            tot += loss.item(); nb += 1
            if nb % 25 == 0:
                print(f'  ep {ep} batch {nb}/{nbatches}  loss {tot/nb:.4f}  '
                      f'{(time.time()-t0)/nb*1000:.0f} ms/batch', flush=True)
        sched.step()
        res = evaluate(model, dv, device)
        eer = res['overall']
        detail = ' '.join(f'{k}={v:.2f}' for k, v in res.items() if k != 'overall')
        print(f'ep {ep:2d}  loss {tot/nb:.4f}  dev EER {eer:.2f}%  ({detail})  {time.time()-t0:.0f}s',
              flush=True)
        logp.write(f'{ep}\t{tot/nb:.4f}\t{eer:.3f}\t{detail}\n'); logp.flush()

        if eer < best - 1e-3:
            best, best_ep, bad = eer, ep, 0
            full = dict(base_sd)
            for k, v in model.conformer.state_dict().items():
                full[f'conformer.{k}'] = v.cpu()
            save_file(full, args.out)
        else:
            bad += 1
            if bad >= args.patience:
                print(f'early stop (no dev improvement for {bad} epochs)')
                break

    logp.close()
    print(f'\nbest dev EER {best:.2f}% at epoch {best_ep}  ->  {args.out}')


if __name__ == '__main__':
    main()
