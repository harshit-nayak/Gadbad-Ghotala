#!/usr/bin/env python3
"""
finetune_language_agnostic.py - Make the deepfake-detection head robust across
languages it hasn't seen, using domain-adversarial training (DANN, Ganin &
Lempitsky 2016) on the existing Hindi/Bengali/Tamil corpus - no new data needed.

Idea: attach a small language-discriminator to the same pooled embedding the
spoof/bonafide classifier uses, through a Gradient Reversal Layer (GRL). The
discriminator is trained normally (to predict language); the GRL flips the
sign of its gradient before it reaches the shared embedding, so the shared
trunk is trained to make language *unpredictable* from that embedding while
staying predictive of spoof-vs-bonafide. If it works, the resulting embedding
carries less language-specific information, and the spoof/bonafide classifier
built on it should generalize better to languages outside hi/bn/ta.

This produces a SEPARATE checkpoint (--out model_indic_ft_agnostic.safetensors)
- the plain hi/bn/ta model (model_indic_ft.safetensors) is left untouched, so
  you can compare the two directly (see evaluate_cross_lingual.py).

Output:
  model_indic_ft_agnostic.safetensors     best full model state dict
  results_indic/finetune_agnostic_log.tsv per-epoch losses, dev EER, dev lang-acc
"""

import argparse, csv, math, os, sys, time
import numpy as np
import torch
import torch.nn as nn
from safetensors.torch import load_file, save_file

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import Model, compute_eer          # noqa: E402
from finetune_indic import FeatSet                     # reuse the same cached-feature dataset

RES = os.path.join(_HERE, 'results_indic')
LANGS = ['hi', 'bn', 'ta']          # fixed order = the discriminator's class indices


class GradReverse(torch.autograd.Function):
    """Identity forward, negated-and-scaled gradient backward."""
    @staticmethod
    def forward(ctx, x, lambd):
        ctx.lambd = lambd
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output):
        return -ctx.lambd * grad_output, None


def grad_reverse(x, lambd):
    return GradReverse.apply(x, lambd)


class LangHead(nn.Module):
    """Small language discriminator - deliberately low-capacity, so it can't
    win the adversarial game by memorizing quirks instead of real cues, and so
    it doesn't starve the (much smaller) spoof-detection signal of capacity."""
    def __init__(self, d_in=144, n_lang=3):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d_in, 64), nn.ReLU(), nn.Linear(64, n_lang))

    def forward(self, x):
        return self.net(x)


def lambda_schedule(progress, gamma=10.0, max_lambda=0.3):
    """Ganin & Lempitsky's ramp: 0 -> max_lambda as training progresses, so the
    adversarial pressure doesn't destabilize the head before it's learned
    anything about spoof detection at all."""
    return max_lambda * (2.0 / (1.0 + math.exp(-gamma * progress)) - 1.0)


def evaluate(model, lang_head, dl, device):
    model.conformer.eval(); lang_head.eval()
    sc, lab, lang, codec, lang_pred = [], [], [], [], []
    with torch.no_grad():
        for h, y, lg, cd in dl:
            out, emb = model.conformer(h.to(device), return_embedding=True)
            sc.extend(out[:, 1].cpu().tolist())
            lang_pred.extend(lang_head(emb).argmax(-1).cpu().tolist())
            lab.extend(y.tolist()); lang.extend(lg); codec.extend(cd)
    sc, lab, lang = np.array(sc), np.array(lab), np.array(lang)
    res = {'overall': compute_eer(lab, sc)}
    for key, arr in [('lang', lang), ('codec', np.array(codec))]:
        for v in sorted(set(arr)):
            m = arr == v
            if 0 < lab[m].sum() < m.sum():
                res[f'{key}:{v}'] = compute_eer(lab[m], sc[m])
    lang_idx = np.array([LANGS.index(l) if l in LANGS else -1 for l in lang])
    valid = lang_idx >= 0
    lang_acc = float((np.array(lang_pred)[valid] == lang_idx[valid]).mean() * 100) if valid.any() else float('nan')
    return res, lang_acc


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--epochs', type=int, default=12)
    pa.add_argument('--batch_size', type=int, default=64)
    pa.add_argument('--lr', type=float, default=3e-4)
    pa.add_argument('--wd', type=float, default=1e-4)
    pa.add_argument('--patience', type=int, default=4)
    pa.add_argument('--train_crop', type=int, default=100)
    pa.add_argument('--max_lambda', type=float, default=0.3,
                    help='ceiling on the adversarial weight (0 = plain fine-tune, '
                         'for an ablation baseline)')
    pa.add_argument('--model_path', default='model.safetensors')
    pa.add_argument('--out', default='model_indic_ft_agnostic.safetensors')
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
    lang_head = LangHead(d_in=144, n_lang=len(LANGS)).to(device)

    ntrain = sum(p.numel() for p in model.conformer.parameters()) / 1e6
    nlh = sum(p.numel() for p in lang_head.parameters())
    print(f'training conformer head: {ntrain:.2f} M params + language discriminator: {nlh} params '
          f'(max_lambda={args.max_lambda})')

    tr = torch.utils.data.DataLoader(FeatSet('train', aug=True, crop=args.train_crop),
                                     batch_size=args.batch_size,
                                     shuffle=True, num_workers=0, drop_last=True)
    dv = torch.utils.data.DataLoader(FeatSet('dev'), batch_size=256, num_workers=0)
    print(f'train {len(tr.dataset)}  dev {len(dv.dataset)}  languages {LANGS}')

    params = list(model.conformer.parameters()) + list(lang_head.parameters())
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=args.wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    lossf = nn.CrossEntropyLoss()

    logp = open(os.path.join(RES, 'finetune_agnostic_log.tsv'), 'w', encoding='utf-8')
    logp.write('epoch\ttrain_spoof_loss\ttrain_lang_loss\tlambda\t'
               'dev_eer_overall\tdev_lang_acc\tdetail\n')
    best, best_ep, bad = 1e9, -1, 0
    nbatches = len(tr)
    total_steps = args.epochs * nbatches
    step = 0

    for ep in range(1, args.epochs + 1):
        model.conformer.train(); lang_head.train()
        t0, tot_s, tot_l, nb = time.time(), 0.0, 0.0, 0
        for h, y, lg, _ in tr:
            h, y = h.to(device), y.to(device)
            lang_idx = torch.tensor([LANGS.index(l) if l in LANGS else 0 for l in lg],
                                    device=device, dtype=torch.long)
            lambd = lambda_schedule(step / max(total_steps, 1), max_lambda=args.max_lambda)

            out, emb = model.conformer(h, return_embedding=True)
            spoof_loss = lossf(out, y)
            lang_logits = lang_head(grad_reverse(emb, lambd))
            lang_loss = lossf(lang_logits, lang_idx)
            loss = spoof_loss + lang_loss   # GRL already flips the sign for the shared trunk

            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(params, 5.0)
            opt.step()
            tot_s += spoof_loss.item(); tot_l += lang_loss.item(); nb += 1; step += 1
            if nb % 25 == 0:
                print(f'  ep {ep} batch {nb}/{nbatches}  spoof_loss {tot_s/nb:.4f}  '
                      f'lang_loss {tot_l/nb:.4f}  lambda {lambd:.3f}  '
                      f'{(time.time()-t0)/nb*1000:.0f} ms/batch', flush=True)
        sched.step()
        res, lang_acc = evaluate(model, lang_head, dv, device)
        eer = res['overall']
        detail = ' '.join(f'{k}={v:.2f}' for k, v in res.items() if k != 'overall')
        print(f'ep {ep:2d}  spoof_loss {tot_s/nb:.4f}  lang_loss {tot_l/nb:.4f}  '
              f'dev EER {eer:.2f}%  dev lang-acc {lang_acc:.1f}% (chance={100/len(LANGS):.1f}%)  '
              f'({detail})  {time.time()-t0:.0f}s', flush=True)
        logp.write(f'{ep}\t{tot_s/nb:.4f}\t{tot_l/nb:.4f}\t{lambd:.3f}\t'
                   f'{eer:.3f}\t{lang_acc:.2f}\t{detail}\n'); logp.flush()

        if eer < best - 1e-3:
            best, best_ep, bad = eer, ep, 0
            full = dict(base_sd)
            for k, v in model.conformer.state_dict().items():
                full[f'conformer.{k}'] = v.cpu()
            save_file(full, args.out)
        else:
            bad += 1
            if bad >= args.patience:
                print(f'early stop (no dev EER improvement for {bad} epochs)')
                break

    logp.close()
    print(f'\nbest dev EER {best:.2f}% at epoch {best_ep}  ->  {args.out}')


if __name__ == '__main__':
    main()
