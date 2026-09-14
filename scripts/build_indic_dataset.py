#!/usr/bin/env python3
"""
build_indic_dataset.py - Assemble a multilingual audio-deepfake-detection corpus.

  real  (bonafide, label 1) : SPRINGLab/IndicVoices-R_{Hindi,Bengali,Tamil}  (48 kHz)
  fake  (spoof,    label 0) : vdivyasharma/IndicSynth  {Hindi,Bengali,Tamil}  (24 kHz)

Streams both datasets with HuggingFace `datasets` (streaming=True, audio decode
disabled -> raw bytes, decoded here with soundfile). Every clip -> 16 kHz mono,
capped at MAX_S s. Speakers split train/dev/test 80/10/10, no speaker crossing.

WhatsApp-style lossy compression (Opus, 16 kHz mono, ~24 kbps, VoIP) is baked in:
  * train    : each clip stored EITHER clean or whatsapp (p=0.5)
  * dev/test : each clip stored BOTH ways (two rows) for per-condition EER

Output:
  indic_df/audio/<lang>/<split>/<real|fake>/<id>[.wa].wav
  indic_df/manifest.tsv   id lang label split codec speaker gender genmodel dur_s path
  indic_df/state.json     stream cursors, for resume

Rerun to resume: already-streamed rows are skipped via saved cursors.
"""

import argparse, csv, hashlib, io, json, os, random, sys, time
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
import av
import warnings
warnings.filterwarnings('ignore')
from datasets import load_dataset, Audio

HERE  = os.path.dirname(os.path.abspath(__file__))
OUT   = os.environ.get('INDIC_DF', r'C:\Users\ATHARV\SIH_data\indic_df')
SR    = 16000
MAX_S = 6.0
MIN_S = 1.0
LANGS = {'Hindi': 'hi', 'Bengali': 'bn', 'Tamil': 'ta', 'Malayalam': 'ml',
         'Gujarati': 'gu', 'Kannada': 'kn', 'Marathi': 'mr'}
# Real-speech source per language: (repo, config, audio_field, needs_bytes_decode, shard_subdir).
# Most real-speech repos store audio as an HF Audio feature under a column named
# 'audio' (encoded bytes, decode=False to skip torchcodec) - asr-malayalam stores
# it as a plain {'array','sampling_rate'} struct instead (no decode needed), and
# the PharynxAI repos use the same Audio-feature/bytes scheme but under a
# differently-named column ('audio_filepath').
REAL_REPOS = {
    'hi': ('SPRINGLab/IndicVoices-R_Hindi', None, 'audio', True, 'data'),
    'bn': ('SPRINGLab/IndicVoices-R_Bengali', None, 'audio', True, 'data'),
    'ta': ('SPRINGLab/IndicVoices-R_Tamil', None, 'audio', True, 'data'),
    'ml': ('asr-malayalam/indicvoices-v1a', None, 'audio', False, 'data'),
    'gu': ('PharynxAI/IndicVoices-gujarati-10000', None, 'audio_filepath', True, 'data'),
    'kn': ('PharynxAI/IndicVoices-kannada-10000', None, 'audio_filepath', True, 'data'),
    'mr': ('PharynxAI/IndicVoices-marathi-10000', None, 'audio_filepath', True, 'data'),
}
FAKE_REPO = 'vdivyasharma/IndicSynth'

from huggingface_hub import HfFileSystem
_fs = HfFileSystem()


def list_shards(repo, subdir):
    """Sorted list of parquet shard filenames (repo-relative) under subdir/."""
    entries = _fs.ls(f'datasets/{repo}/{subdir}', detail=True)
    prefix = f'{repo}/'
    return sorted(e['name'].split(prefix, 1)[1] for e in entries if e['name'].endswith('.parquet'))


def to_mono16k(wav, sr):
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    wav = wav.astype(np.float32)
    if sr != SR:
        g = np.gcd(int(sr), SR)
        wav = resample_poly(wav, SR // g, sr // g).astype(np.float32)
    return wav


def whatsapp_opus(wav):
    buf = io.BytesIO()
    cont = av.open(buf, 'w', format='ogg')
    st = cont.add_stream('libopus', rate=SR)
    st.bit_rate = 24000
    try:
        st.layout = 'mono'
    except Exception:
        pass
    fr = av.AudioFrame.from_ndarray(wav.reshape(1, -1), format='flt', layout='mono')
    fr.sample_rate = SR
    for p in st.encode(fr):
        cont.mux(p)
    for p in st.encode(None):
        cont.mux(p)
    cont.close()
    buf.seek(0)
    dec = av.open(buf, 'r')
    chunks = [f.to_ndarray().reshape(-1) for f in dec.decode(audio=0)]
    dec.close()
    y = np.concatenate(chunks).astype(np.float32) if chunks else wav
    return resample_poly(y, SR, 48000).astype(np.float32)   # libopus decodes at 48k


def trim(wav):
    n = int(MAX_S * SR)
    if len(wav) > n:
        s = (len(wav) - n) // 2
        wav = wav[s:s + n]
    return wav


def split_for(speaker, seed=0):
    h = int(hashlib.md5(f'{seed}:{speaker}'.encode()).hexdigest(), 16) % 10
    return 'train' if h < 8 else ('dev' if h == 8 else 'test')


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument('--target_gb', type=float, default=6.0)
    pa.add_argument('--seed', type=int, default=0)
    pa.add_argument('--max_stream', type=int, default=400000,
                    help='hard cap on rows streamed per (lang,class)')
    args = pa.parse_args()
    random.seed(args.seed)
    os.makedirs(OUT, exist_ok=True)

    man_path = os.path.join(OUT, 'manifest.tsv')
    state_path = os.path.join(OUT, 'state.json')
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    done = set()
    have = {}
    if os.path.exists(man_path):
        for d in csv.DictReader(open(man_path, encoding='utf-8'), delimiter='\t'):
            done.add((d['lang'], d['label'], d['id']))
            try:
                have[(d['lang'], d['label'])] = have.get((d['lang'], d['label']), 0) + os.path.getsize(d['path'])
            except OSError:
                pass

    budget = args.target_gb * 1e9 / (len(LANGS) * 2)
    print(f'target {args.target_gb} GB -> {budget/1e9:.2f} GB per (lang,class); resuming {len(done)} rows', flush=True)

    man_f = open(man_path, 'a', encoding='utf-8', newline='')
    man_w = csv.writer(man_f, delimiter='\t')
    if not done:
        man_w.writerow(['id', 'lang', 'label', 'split', 'codec', 'speaker',
                        'gender', 'genmodel', 'dur_s', 'path'])
        man_f.flush()

    def emit(uid, lang, label, split, speaker, gender, genmodel, wav):
        sub = 'real' if label == 1 else 'fake'
        d = os.path.join(OUT, 'audio', lang, split, sub)
        os.makedirs(d, exist_ok=True)
        variants = ([('whatsapp' if random.random() < 0.5 else 'clean', '')]
                    if split == 'train' else [('clean', ''), ('whatsapp', '.wa')])
        nb = 0
        for codec, suf in variants:
            y = np.clip(whatsapp_opus(wav) if codec == 'whatsapp' else wav, -1.0, 1.0)
            p = os.path.join(d, f'{uid}{suf}.wav')
            sf.write(p, y, SR, subtype='PCM_16')
            nb += os.path.getsize(p)
            man_w.writerow([uid, lang, label, split, codec, speaker, gender,
                            genmodel, f'{len(y)/SR:.2f}', p])
        man_f.flush()
        return nb

    # Shard-level resume: state[key] = index of the next not-yet-consumed shard.
    # A restart re-fetches at worst the ONE shard that was in progress, never the
    # whole stream from row 0 - unlike a single continuous .skip(cursor) stream,
    # where a restart has to re-download and discard every row already seen.
    _shard_state = {}

    def _shards_for(key, repo, shard_subdir):
        if key not in _shard_state:
            shards = list_shards(repo, shard_subdir)
            _shard_state[key] = {'shards': shards, 'idx': state.get(key, 0), 'iter': None}
        return _shard_state[key]

    def run(lang, lcode, label, repo, config, spk_fields, gender_field, gm_field, txt_field,
            needs_decode, shard_subdir, audio_field, *, sub_budget):
        """Fill this bucket up to sub_budget bytes (a slice of the round), then return."""
        key = f'{lcode}:{label}'
        lbl = str(label)
        cap = min(sub_budget, budget)
        if have.get((lcode, lbl), 0) >= cap:
            return
        st = _shards_for(key, repo, shard_subdir)

        while have.get((lcode, lbl), 0) < cap and st['idx'] < len(st['shards']):
            if st['iter'] is None:
                shard_file = st['shards'][st['idx']]
                try:
                    ds = load_dataset(repo, config, data_files={'train': [shard_file]},
                                      split='train', streaming=True)
                    if needs_decode:
                        ds = ds.cast_column(audio_field, Audio(decode=False))
                    st['iter'] = iter(ds)
                except Exception as e:
                    print(f'  [{key}] shard open failed ({e!r}); retry next round', flush=True)
                    time.sleep(15)
                    return
            try:
                n_this_shard = 0
                for ex in st['iter']:
                    n_this_shard += 1
                    if have.get((lcode, lbl), 0) >= cap:
                        return   # pause mid-shard; st['iter'] kept, resumes same shard next round
                    spk = 'unk'
                    for fld in spk_fields:
                        if ex.get(fld) not in (None, ''):
                            spk = str(ex[fld]); break
                    gm = str(ex.get(gm_field, '')) if gm_field else ''
                    au = ex[audio_field]
                    if needs_decode:
                        # HF Audio feature, decode=False -> {'bytes':..., 'path':...}
                        b = au.get('bytes') if isinstance(au, dict) else au
                        if not b:
                            continue
                        dedup_key = str(len(b))
                        try:
                            w, sr = sf.read(io.BytesIO(b), dtype='float32')
                        except Exception:
                            continue
                    else:
                        # plain {'array','sampling_rate'} struct, already decoded
                        arr = au.get('array')
                        if arr is None or len(arr) == 0:
                            continue
                        w = np.asarray(arr, dtype='float32')
                        sr = au.get('sampling_rate', SR)
                        dedup_key = str(len(w))
                    uid = f'{lcode}_{"r" if label==1 else "f"}_' + hashlib.md5(
                        (spk + '|' + gm + '|' + str(ex.get(txt_field, '')) + '|' + dedup_key).encode()
                    ).hexdigest()[:16]
                    if (lcode, str(label), uid) in done:
                        continue
                    w = to_mono16k(w, sr)
                    if len(w) < MIN_S * SR:
                        continue
                    w = trim(w)
                    sp = split_for(('r' if label == 1 else 'f') + spk, args.seed)
                    nb = emit(uid, lcode, label, sp, spk, str(ex.get(gender_field, '')), gm, w)
                    have[(lcode, lbl)] = have.get((lcode, lbl), 0) + nb
                    done.add((lcode, str(label), uid))
                    if n_this_shard % 200 == 0:
                        print(f'  [{key}] shard {st["idx"]+1}/{len(st["shards"])}: '
                              f'{n_this_shard} rows, {have[(lcode,lbl)]/1e9:.2f}/{budget/1e9:.2f} GB',
                              flush=True)
                # shard exhausted
                st['idx'] += 1
                st['iter'] = None
                state[key] = st['idx']
                json.dump(state, open(state_path, 'w'))
                print(f'  [{key}] shard {st["idx"]}/{len(st["shards"])} done, '
                      f'{have.get((lcode,lbl),0)/1e9:.2f}/{budget/1e9:.2f} GB', flush=True)
            except Exception as e:
                print(f'  [{key}] stream error mid-shard ({e!r}); retrying same shard next round',
                      flush=True)
                st['iter'] = None       # redo this one shard, not the whole bucket
                time.sleep(15)
                return
        if st['idx'] >= len(st['shards']):
            print(f'  [{key}] all {len(st["shards"])} shards exhausted, '
                  f'final {have.get((lcode,lbl),0)/1e9:.2f} GB', flush=True)

    buckets = []
    for LNAME, lcode in LANGS.items():
        real_repo, real_cfg, real_audio_field, real_decode, real_subdir = REAL_REPOS[lcode]
        buckets.append((LNAME, lcode, 1, real_repo, real_cfg,
                        ['speaker_id'], 'gender', None, 'text', real_decode, real_subdir,
                        real_audio_field))
        buckets.append((LNAME, lcode, 0, FAKE_REPO, LNAME,
                        ['Target Speaker ID', 'Source Speaker_ID'], 'Gender',
                        'Generative Model', 'TTS Transcript', True, LNAME, 'audio'))

    def bucket_exhausted(lcode, label):
        st = _shard_state.get(f'{lcode}:{label}')
        return st is not None and st['idx'] >= len(st['shards'])

    def bucket_pending(b):
        lcode, label = b[1], b[2]
        return have.get((lcode, str(label)), 0) < budget and not bucket_exhausted(lcode, label)

    STEP = 0.35e9
    rt = STEP
    # Resuming into shards already consumed under the old row-cursor scheme means
    # early rounds can add near-zero NEW bytes (everything dedups) before reaching
    # fresh data - so stop only on true exhaustion (every shard list drained), not
    # on a single unproductive round.
    while any(bucket_pending(b) for b in buckets):
        for b in buckets:
            if bucket_pending(b):
                run(*b, sub_budget=rt)
        rt = min(rt + STEP, budget)

    man_f.close()
    total = sum(have.values())
    print(f'\ndone. ~{total/1e9:.2f} GB, {len(done)} source clips', flush=True)
    for k, v in sorted(have.items()):
        print(f'  {k}: {v/1e9:.2f} GB', flush=True)


if __name__ == '__main__':
    main()
