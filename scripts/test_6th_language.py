#!/usr/bin/env python3
"""
test_6th_language.py - True zero-shot test: score the 5-language checkpoint
(model_indic_ft_5lang.safetensors, trained on hi/bn/ta/ml/gu) on Kannada, a
language it has NEVER seen in training, dev, or test. This is exactly the gap
the report's report flags in §12/§13: once ml+gu were folded into training,
no held-out language remained in the corpus - this pulls in a fresh 6th one
to actually measure it instead of leaving it untested.

Real speech:  PharynxAI/IndicVoices-kannada-10000  (same source family as the
              gu/kn/mr repos already wired into build_indic_dataset.py)
Fake speech:  vdivyasharma/IndicSynth/Kannada       (same generator family as
              every other language in the corpus)

Downloads a small fresh sample (not the full corpus), preprocesses identically
to build_indic_dataset.py (mono 16k, trimmed to <=6s), saves wavs under
indic_df/audio/kn/test6th/ for reproducibility, then scores with the full
model (backbone + head) and reports both its own-threshold EER and accuracy
at the report's fixed deployment threshold.
"""
import argparse, csv, hashlib, io, os, sys
import numpy as np
import soundfile as sf
import torch
from datasets import load_dataset, Audio
from safetensors.torch import load_file

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from build_indic_dataset import list_shards, to_mono16k, trim, SR, MIN_S   # noqa: E402
from evaluate_model import Model, pad_or_trim, compute_eer                  # noqa: E402
from confusion_all_languages import confusion, report                       # noqa: E402

OUT = os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df')
LCODE, LNAME = 'kn', 'Kannada'
REAL_REPO, REAL_SUBDIR, REAL_FIELD = 'PharynxAI/IndicVoices-kannada-10000', 'data', 'audio_filepath'
FAKE_REPO, FAKE_SUBDIR, FAKE_FIELD = 'vdivyasharma/IndicSynth', LNAME, 'audio'
CUT = 66800
FIXED_THRESHOLD = -1.0212   # from confusion_all_languages_5lang.csv: EER pt on hi/bn/ta test, this ckpt


def collect(repo, config, subdir, audio_field, label, n_target):
    """Stream shards, decode audio, mono16k + trim, stop once n_target collected."""
    shards = list_shards(repo, subdir)
    out = []
    for shard_file in shards:
        if len(out) >= n_target:
            break
        try:
            ds = load_dataset(repo, config, data_files={'train': [shard_file]},
                              split='train', streaming=True)
            ds = ds.cast_column(audio_field, Audio(decode=False))
        except Exception as e:
            print(f'  shard open failed ({shard_file}): {e!r}, skipping')
            continue
        for ex in ds:
            if len(out) >= n_target:
                break
            au = ex[audio_field]
            b = au.get('bytes') if isinstance(au, dict) else au
            if not b:
                continue
            try:
                w, sr = sf.read(io.BytesIO(b), dtype='float32')
            except Exception:
                continue
            w = to_mono16k(w, sr)
            if len(w) < MIN_S * SR:
                continue
            w = trim(w)
            uid = f'{LCODE}_{"r" if label==1 else "f"}_' + hashlib.md5(b[:256]).hexdigest()[:16]
            out.append((uid, w))
        print(f'  [{"real" if label==1 else "fake"}] shard {shard_file.split("/")[-1]}: '
              f'{len(out)}/{n_target} collected so far', flush=True)
    return out


def save_and_manifest(real_clips, fake_clips):
    man_rows = []
    for label, clips in [(1, real_clips), (0, fake_clips)]:
        sub = 'real' if label == 1 else 'fake'
        d = os.path.join(OUT, 'audio', LCODE, 'test6th', sub)
        os.makedirs(d, exist_ok=True)
        for uid, w in clips:
            p = os.path.join(d, f'{uid}.wav')
            sf.write(p, np.clip(w, -1.0, 1.0), SR, subtype='PCM_16')
            man_rows.append({'id': uid, 'lang': LCODE, 'label': str(label), 'split': 'test6th',
                             'codec': 'clean', 'speaker': 'unk', 'genmodel': '',
                             'dur_s': f'{len(w)/SR:.2f}', 'path': p})
    man_path = os.path.join(OUT, 'manifest_kn6th.tsv')
    with open(man_path, 'w', encoding='utf-8', newline='') as f:
        w_ = csv.DictWriter(f, fieldnames=['id', 'lang', 'label', 'split', 'codec', 'speaker',
                                           'genmodel', 'dur_s', 'path'], delimiter='\t')
        w_.writeheader()
        w_.writerows(man_rows)
    print(f'wrote {man_path}  ({len(man_rows)} clips)')
    return man_rows


@torch.no_grad()
def score(model, rows, device, batch_size=32):
    scores = np.zeros(len(rows))
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        wavs = []
        for r in batch:
            w, _ = sf.read(r['path'], dtype='float32')
            wavs.append(pad_or_trim(w, CUT).astype(np.float32))
        x = torch.from_numpy(np.stack(wavs)).to(device)
        out = model(x)
        scores[i:i + len(batch)] = out[:, 1].cpu().numpy()
    return scores


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--model_path', default='model_indic_ft_5lang.safetensors')
    pa.add_argument('--n_per_class', type=int, default=250)
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    args = pa.parse_args()
    device = torch.device(args.device)

    print(f'Collecting {args.n_per_class} real Kannada clips from {REAL_REPO} ...')
    real_clips = collect(REAL_REPO, None, REAL_SUBDIR, REAL_FIELD, 1, args.n_per_class)
    print(f'Collecting {args.n_per_class} fake Kannada clips from {FAKE_REPO}/{FAKE_SUBDIR} ...')
    fake_clips = collect(FAKE_REPO, LNAME, FAKE_SUBDIR, FAKE_FIELD, 0, args.n_per_class)
    print(f'collected: real={len(real_clips)} fake={len(fake_clips)}')

    man_rows = save_and_manifest(real_clips, fake_clips)

    model = Model(emb_size=144, num_encoders=12)
    sd = load_file(args.model_path, device='cpu')
    miss, unexp = model.load_state_dict(sd, strict=False)
    if miss or unexp:
        raise SystemExit(f'{args.model_path}: tensor mismatch ({len(miss)} missing, {len(unexp)} unexpected)')
    model.eval().to(device)
    print(f'model: {args.model_path}')

    s = score(model, man_rows, device)
    y = np.array([int(r['label']) for r in man_rows])
    print(f'\n=== KANNADA - genuinely never seen in training/dev/test ===')
    own_eer = compute_eer(y, s)
    print(f'own-threshold EER: {own_eer:.2f}%')
    report(f'=== kn [NEVER TRAINED, fixed threshold {FIXED_THRESHOLD}] ===', y, s, FIXED_THRESHOLD)

    csv_out = 'results_indic/eval_6th_language_kn.csv'
    with open(csv_out, 'w', newline='', encoding='utf-8') as f:
        w_ = csv.writer(f)
        w_.writerow(['lang', 'n', 'n_real', 'n_fake', 'own_threshold_eer_pct', 'fixed_threshold', 'note'])
        w_.writerow(['kn', len(y), int(y.sum()), int((1 - y).sum()), f'{own_eer:.2f}',
                    FIXED_THRESHOLD, 'never seen in training/dev/test - true zero-shot'])
    print(f'\n-> {csv_out}')


if __name__ == '__main__':
    main()
