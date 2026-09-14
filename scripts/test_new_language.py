#!/usr/bin/env python3
"""
test_new_language.py - True zero-shot test: score the 5-language checkpoint
(model_indic_ft_5lang.safetensors, trained on hi/bn/ta/ml/gu) on a language it
has NEVER seen in training/dev/test. Generalized version of the Kannada probe
in test_6th_language.py, parameterized so it can be pointed at any language
with a real-speech repo + a vdivyasharma/IndicSynth fake-speech folder.

Real speech repo must expose either an HF Audio feature (encoded bytes,
decode=False) or the plain {'array','sampling_rate'} struct - same two shapes
build_indic_dataset.py already handles.
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
from confusion_all_languages import report                                  # noqa: E402

OUT = os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df')
CUT = 66800
FIXED_THRESHOLD = -1.0212   # from confusion_all_languages_5lang.csv: EER pt on hi/bn/ta test, this ckpt


def collect(lcode, repo, config, subdir, audio_field, needs_decode, label, n_target):
    shards = list_shards(repo, subdir)
    out = []
    for shard_file in shards:
        if len(out) >= n_target:
            break
        try:
            ds = load_dataset(repo, config, data_files={'train': [shard_file]},
                              split='train', streaming=True)
            if needs_decode:
                ds = ds.cast_column(audio_field, Audio(decode=False))
        except Exception as e:
            print(f'  shard open failed ({shard_file}): {e!r}, skipping')
            continue
        try:
            for ex in ds:
                if len(out) >= n_target:
                    break
                au = ex[audio_field]
                if needs_decode:
                    b = au.get('bytes') if isinstance(au, dict) else au
                    if not b:
                        continue
                    try:
                        w, sr = sf.read(io.BytesIO(b), dtype='float32')
                    except Exception:
                        continue
                    dedup_key = b[:256] if isinstance(b, bytes) else str(b)[:256]
                else:
                    arr = au.get('array')
                    if arr is None or len(arr) == 0:
                        continue
                    w = np.asarray(arr, dtype='float32')
                    sr = au.get('sampling_rate', SR)
                    dedup_key = str(len(w)).encode()
                w = to_mono16k(w, sr)
                if len(w) < MIN_S * SR:
                    continue
                w = trim(w)
                uid = f'{lcode}_{"r" if label==1 else "f"}_' + hashlib.md5(dedup_key).hexdigest()[:16]
                out.append((uid, w))
        except Exception as e:
            print(f'  shard stream error ({shard_file}): {e!r}, moving on')
            continue
        print(f'  [{"real" if label==1 else "fake"}] shard {shard_file.split("/")[-1]}: '
              f'{len(out)}/{n_target} collected so far', flush=True)
    return out


def save_and_manifest(lcode, real_clips, fake_clips):
    man_rows = []
    for label, clips in [(1, real_clips), (0, fake_clips)]:
        sub = 'real' if label == 1 else 'fake'
        d = os.path.join(OUT, 'audio', lcode, 'testNth', sub)
        os.makedirs(d, exist_ok=True)
        for uid, w in clips:
            p = os.path.join(d, f'{uid}.wav')
            sf.write(p, np.clip(w, -1.0, 1.0), SR, subtype='PCM_16')
            man_rows.append({'id': uid, 'lang': lcode, 'label': str(label), 'split': 'testNth',
                             'codec': 'clean', 'speaker': 'unk', 'genmodel': '',
                             'dur_s': f'{len(w)/SR:.2f}', 'path': p})
    man_path = os.path.join(OUT, f'manifest_{lcode}Nth.tsv')
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
    pa.add_argument('--lcode', required=True)
    pa.add_argument('--lname', required=True, help='language name as used by the IndicSynth fake-repo subfolder')
    pa.add_argument('--real_repo', required=True)
    pa.add_argument('--real_config', default=None)
    pa.add_argument('--real_subdir', default='data')
    pa.add_argument('--real_field', default='audio')
    pa.add_argument('--real_needs_decode', type=int, default=1)
    pa.add_argument('--model_path', default='model_indic_ft_5lang.safetensors')
    pa.add_argument('--n_per_class', type=int, default=250)
    pa.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    args = pa.parse_args()
    device = torch.device(args.device)

    print(f'=== {args.lname} ({args.lcode}) ===')
    print(f'Collecting {args.n_per_class} real clips from {args.real_repo} ...')
    real_clips = collect(args.lcode, args.real_repo, args.real_config, args.real_subdir,
                         args.real_field, bool(args.real_needs_decode), 1, args.n_per_class)
    print(f'Collecting {args.n_per_class} fake clips from vdivyasharma/IndicSynth/{args.lname} ...')
    fake_clips = collect(args.lcode, 'vdivyasharma/IndicSynth', args.lname, args.lname,
                         'audio', True, 0, args.n_per_class)
    print(f'collected: real={len(real_clips)} fake={len(fake_clips)}')

    if not real_clips or not fake_clips:
        print(f'!! insufficient data for {args.lname} (real={len(real_clips)}, fake={len(fake_clips)}) - aborting')
        return

    man_rows = save_and_manifest(args.lcode, real_clips, fake_clips)

    model = Model(emb_size=144, num_encoders=12)
    sd = load_file(args.model_path, device='cpu')
    miss, unexp = model.load_state_dict(sd, strict=False)
    if miss or unexp:
        raise SystemExit(f'{args.model_path}: tensor mismatch ({len(miss)} missing, {len(unexp)} unexpected)')
    model.eval().to(device)

    s = score(model, man_rows, device)
    y = np.array([int(r['label']) for r in man_rows])
    own_eer = compute_eer(y, s)
    print(f'\nown-threshold EER: {own_eer:.2f}%')
    r = report(f'=== {args.lcode} [NEVER TRAINED, fixed threshold {FIXED_THRESHOLD}] ===', y, s, FIXED_THRESHOLD)

    os.makedirs('results_indic', exist_ok=True)
    csv_out = f'results_indic/eval_new_language_{args.lcode}.csv'
    write_header = not os.path.exists('results_indic/eval_new_languages_all.csv')
    with open('results_indic/eval_new_languages_all.csv', 'a', newline='', encoding='utf-8') as f:
        w_ = csv.writer(f)
        if write_header:
            w_.writerow(['lang', 'lname', 'n', 'n_real', 'n_fake', 'TP', 'FN', 'FP', 'TN',
                        'accuracy_pct', 'own_threshold_eer_pct', 'fixed_threshold'])
        w_.writerow([args.lcode, args.lname, len(y), int(y.sum()), int((1 - y).sum()),
                    r['tp'], r['fn'], r['fp'], r['tn'], f"{r['acc']:.2f}", f'{own_eer:.2f}', FIXED_THRESHOLD])
    print(f'\n-> appended to results_indic/eval_new_languages_all.csv')


if __name__ == '__main__':
    main()
