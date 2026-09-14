#!/usr/bin/env python3
"""
extract_head_diff.py - Extract just the tensors that differ from the base
checkpoint (the fine-tuned head) into a small standalone safetensors file, and
verify the reconstruction (base + diff) is byte-identical to the full checkpoint.

Same idea as the original conformer_head_only.safetensors in
release/xlsr-mamba-indic-ft-lite.zip, generalized to any checkpoint.
"""
import argparse
import torch
from safetensors.torch import load_file, save_file


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--base', default='model.safetensors')
    pa.add_argument('--full', required=True)
    pa.add_argument('--out', required=True)
    args = pa.parse_args()

    base = load_file(args.base, device='cpu')
    full = load_file(args.full, device='cpu')

    diff = {k: v for k, v in full.items() if k not in base or not torch.equal(v, base[k])}
    print(f'{args.full}: {len(diff)}/{len(full)} tensors differ from {args.base}')

    # verify: base merged with diff must reconstruct `full` exactly
    recon = dict(base)
    recon.update(diff)
    assert set(recon.keys()) == set(full.keys()), 'key set mismatch after reconstruction'
    for k in full:
        assert torch.equal(recon[k], full[k]), f'reconstruction mismatch at {k}'
    print('reconstruction verified byte-identical.')

    save_file(diff, args.out)
    import os
    print(f'-> {args.out}  ({os.path.getsize(args.out)/1e6:.1f} MB)')


if __name__ == '__main__':
    main()
