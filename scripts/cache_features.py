#!/usr/bin/env python3
"""
cache_features.py - Precompute frozen-backbone features for the Indic corpus.

Fine-tuning freezes the XLSR wav2vec-2.0 backbone AND the LL / first_bn front-end,
and trains only the Mamba conformer head. That makes the conformer input
    h = SELU(first_bn(LL(xlsr_features)))          # shape [T, 144]
a static function of the waveform, so we compute it once here and memmap it to
disk. Training then runs in seconds/epoch with no backbone forward.

Output:
  indic_df/feat/<split>.dat     float16 memmap  [N, T, 144]
  indic_df/feat/<split>.tsv     row -> id, lang, label, codec, speaker, genmodel
"""

import argparse, csv, os, sys
import numpy as np
import torch
from safetensors.torch import load_file
from tqdm import tqdm

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from evaluate_model import Model, pad_or_trim   # noqa: E402

OUT   = os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df')
CUT   = 66800
TFRAMES = 208            # wav2vec2 frames for CUT samples (320x downsample)
FDIM  = 144


def front_end(model, wav_batch, device):
    """xlsr -> LL -> first_bn -> SELU   (all frozen).  returns [B, T, 144]."""
    feat, _ = model.ssl_model.extract_feat(wav_batch.to(device))
    x = model.LL(feat)
    x = model.selu(model.first_bn(x.unsqueeze(1))).squeeze(1)
    return x


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--manifest', default=os.path.join(OUT, 'manifest.tsv'))
    pa.add_argument('--model_path', default='model.safetensors')
    pa.add_argument('--batch_size', type=int, default=16)
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    pa.add_argument('--splits', default='train,dev,test')
    args = pa.parse_args()
    device = torch.device(args.device)

    rows = list(csv.DictReader(open(args.manifest, encoding='utf-8'), delimiter='\t'))
    print(f'manifest: {len(rows)} rows')

    model = Model(emb_size=144, num_encoders=12)
    sd = load_file(args.model_path, device='cpu')
    miss, unexp = model.load_state_dict(sd, strict=False)
    assert not miss and not unexp, (len(miss), len(unexp))
    model.eval().to(device)
    for p in model.parameters():
        p.requires_grad_(False)

    import soundfile as sf
    os.makedirs(os.path.join(OUT, 'feat'), exist_ok=True)

    for split in args.splits.split(','):
        srows = [r for r in rows if r['split'] == split]
        if not srows:
            continue
        N = len(srows)
        datp = os.path.join(OUT, 'feat', f'{split}.dat')
        mm = np.memmap(datp, dtype='float16', mode='w+', shape=(N, TFRAMES, FDIM))
        with open(os.path.join(OUT, 'feat', f'{split}.tsv'), 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter='\t')
            w.writerow(['row', 'id', 'lang', 'label', 'codec', 'speaker', 'genmodel'])
            for i, r in enumerate(srows):
                w.writerow([i, r['id'], r['lang'], r['label'], r['codec'],
                            r['speaker'], r['genmodel']])

        buf, idxs = [], []
        def flush():
            if not buf:
                return
            wav = torch.from_numpy(np.stack(buf)).float()
            with torch.no_grad():
                h = front_end(model, wav, device)          # [B,T,144]
            h = h[:, :TFRAMES].cpu().numpy().astype('float16')
            if h.shape[1] < TFRAMES:
                h = np.pad(h, ((0, 0), (0, TFRAMES - h.shape[1]), (0, 0)))
            for k, gi in enumerate(idxs):
                mm[gi] = h[k]
            buf.clear(); idxs.clear()

        for i, r in enumerate(tqdm(srows, desc=f'  {split}')):
            try:
                x, sr = sf.read(r['path'], dtype='float32')
                if x.ndim > 1:
                    x = x[:, 0]
            except Exception:
                x = np.zeros(CUT, dtype=np.float32)
            x = pad_or_trim(x, CUT).astype(np.float32)
            buf.append(x); idxs.append(i)
            if len(buf) == args.batch_size:
                flush()
        flush()
        mm.flush()
        print(f'  {split}: wrote {datp}  {os.path.getsize(datp)/1e9:.2f} GB  [{N},{TFRAMES},{FDIM}]')


if __name__ == '__main__':
    main()
