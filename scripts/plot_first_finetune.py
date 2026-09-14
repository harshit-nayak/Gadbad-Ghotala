#!/usr/bin/env python3
"""
plot_first_finetune.py - Ultralytics-results.png-style grid of training curves
for the very first hi/bn/ta-only fine-tune (finetune_indic.py -> model_indic_ft.safetensors).

That run's finetune_log.tsv has since been overwritten by the later 5-language
retrain (same default output path), but every per-epoch number survives in the
original console log, results_indic/finetune_run.log - this just re-parses it.

Only 4 epochs completed before the epoch-5 CUDA OOM crash (see log), so each
panel has 4 points - small multiples, blue line + light dashed trend, same
visual language as the pasted reference image.
"""
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

LOG = 'results_indic/finetune_run.log'

rows = []
pat = re.compile(
    r'^ep\s+(\d+)\s+loss\s+([\d.]+)\s+dev EER\s+([\d.]+)%\s+\((.*?)\)'
)
with open(LOG, encoding='utf-8') as f:
    for line in f:
        m = pat.match(line.strip())
        if not m:
            continue
        ep, loss, eer, detail = m.groups()
        d = dict(kv.split('=') for kv in detail.split())
        rows.append({
            'epoch': int(ep), 'loss': float(loss), 'dev_eer': float(eer),
            'bn': float(d['lang:bn']), 'hi': float(d['lang:hi']), 'ta': float(d['lang:ta']),
            'clean': float(d['codec:clean']), 'whatsapp': float(d['codec:whatsapp']),
        })

epochs = [r['epoch'] for r in rows]
print(f'parsed {len(rows)} epochs: {epochs}')

panels = [
    ('train/loss', 'loss', '#3d7fc9'),
    ('metrics/dev_EER(overall)', 'dev_eer', '#c9463d'),
    ('metrics/EER(bn)', 'bn', '#d95926'),
    ('metrics/EER(hi)', 'hi', '#3987e5'),
    ('metrics/EER(ta)', 'ta', '#199e70'),
    ('metrics/EER(clean)', 'clean', '#7a5cc9'),
    ('metrics/EER(whatsapp)', 'whatsapp', '#c98f3d'),
]

fig, axes = plt.subplots(2, 4, figsize=(16, 6.4))
fig.patch.set_facecolor('white')
axes = axes.flatten()

for ax, (title, key, color) in zip(axes, panels):
    y = np.array([r[key] for r in rows])
    x = np.array(epochs)
    ax.plot(x, y, marker='o', markersize=4.5, linewidth=1.6, color=color, label='results')
    if len(x) >= 3:
        coeffs = np.polyfit(x, y, deg=min(2, len(x) - 1))
        xs = np.linspace(x.min(), x.max(), 60)
        ax.plot(xs, np.polyval(coeffs, xs), linestyle='--', linewidth=1.3,
                color='#e08a2b', alpha=0.85, label='smooth')
    ax.set_title(title, fontsize=10.5, fontweight='medium')
    ax.set_xlabel('epoch', fontsize=8.5)
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.tick_params(labelsize=8)
    ax.set_xticks(x)
    ax.legend(fontsize=7, frameon=False, loc='best')

# 8th panel: annotation about the crash
ax = axes[7]
ax.axis('off')
ax.text(0.02, 0.85, 'First fine-tune of the plain\n(non-adversarial) head on\nHindi + Bengali + Tamil',
        fontsize=10.5, fontweight='bold', va='top', transform=ax.transAxes)
ax.text(0.02, 0.45,
        'Training crashed at epoch 5 with a\nCUDA out-of-memory error (concurrent\n'
        'CPU eval job pushed VRAM over the\n8GB ceiling). Epoch 4 - already the\n'
        'best dev EER (0.63%) - was kept as\nthe final checkpoint.',
        fontsize=9, va='top', transform=ax.transAxes, color='#444')

fig.suptitle('First hi/bn/ta fine-tune - training curves (finetune_indic.py → model_indic_ft.safetensors)',
            fontsize=12.5, fontweight='bold', y=1.02)
fig.tight_layout()
out = 'results_indic/first_finetune_curves.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f'-> {out}')
