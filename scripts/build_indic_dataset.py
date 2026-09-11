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
LANGS = {'Hindi': 'hi', 'Bengali': 'bn', 'Tamil': 'ta'}
REAL_REPO = 'SPRINGLab/IndicVoices-R_{lang}'
FAKE_REPO = 'vdivyasharma/IndicSynth'


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

    # persistent iterator per bucket, so round-robin filling resumes cheaply
    _iters = {}

    def _mk_iter(repo, config, cursor):
        ds = load_dataset(repo, config, split='train', streaming=True)
        ds = ds.cast_column('audio', Audio(decode=False))
        if cursor:
            ds = ds.skip(cursor)
        return iter(ds)

    def run(lang, lcode, label, repo, config, spk_fields, gender_field, gm_field, txt_field,
            sub_budget):
        """Fill this bucket up to sub_budget bytes (a slice of the round), then return."""
        key = f'{lcode}:{label}'
        lbl = str(label)
        if have.get((lcode, lbl), 0) >= min(sub_budget, budget):
            return
        cursor = state.get(key, 0)
        if key not in _iters:
            _iters[key] = _mk_iter(repo, config, cursor)
        for attempt in range(6):
            try:
                it = _iters[key]
                for ex in it:
                    cursor += 1
                    if cursor >= args.max_stream:
                        break
                    if have.get((lcode, lbl), 0) >= min(sub_budget, budget):
                        break
                    spk = 'unk'
                    for fld in spk_fields:
                        if ex.get(fld) not in (None, ''):
                            spk = str(ex[fld]); break
                    gm = str(ex.get(gm_field, '')) if gm_field else ''
                    b = ex['audio']['bytes']
                    if not b:
                        continue
                    uid = f'{lcode}_{"r" if label==1 else "f"}_' + hashlib.md5(
                        (spk + '|' + gm + '|' + str(ex.get(txt_field, '')) + '|' + str(len(b))).encode()
                    ).hexdigest()[:16]
                    if (lcode, str(label), uid) in done:
                        continue
                    try:
                        w, sr = sf.read(io.BytesIO(b), dtype='float32')
                    except Exception:
                        continue
                    w = to_mono16k(w, sr)
                    if len(w) < MIN_S * SR:
                        continue
                    w = trim(w)
                    sp = split_for(('r' if label == 1 else 'f') + spk, args.seed)
                    nb = emit(uid, lcode, label, sp, spk, str(ex.get(gender_field, '')), gm, w)
                    have[(lcode, str(label))] = have.get((lcode, str(label)), 0) + nb
                    done.add((lcode, str(label), uid))
                    if cursor % 200 == 0:
                        state[key] = cursor
                        json.dump(state, open(state_path, 'w'))
                        print(f'  [{key}] {cursor} streamed, {have[(lcode,str(label))]/1e9:.2f}/{budget/1e9:.2f} GB', flush=True)
                break
            except Exception as e:
                print(f'  [{key}] stream error ({e!r}); saving cursor {cursor}, will resume next round', flush=True)
                state[key] = cursor
                json.dump(state, open(state_path, 'w'))
                _iters.pop(key, None)          # recreate once, next round
                time.sleep(20)
                break
        state[key] = cursor
        json.dump(state, open(state_path, 'w'))

    buckets = []
    for LNAME, lcode in LANGS.items():
        buckets.append((LNAME, lcode, 1, REAL_REPO.format(lang=LNAME), None,
                        ['speaker_id'], 'gender', None, 'text'))
        buckets.append((LNAME, lcode, 0, FAKE_REPO, LNAME,
                        ['Target Speaker ID', 'Source Speaker_ID'], 'Gender',
                        'Generative Model', 'TTS Transcript'))

    STEP = 0.35e9
    rt = STEP
    while any(have.get((b[1], str(b[2])), 0) < budget for b in buckets):
        before = sum(have.values())
        for b in buckets:
            run(*b, sub_budget=rt)
        rt = min(rt + STEP, budget)
        if sum(have.values()) - before < 1e6:      # a full pass added <1 MB -> data exhausted
            print('  (sources exhausted before target)', flush=True)
            break

    man_f.close()
    total = sum(have.values())
    print(f'\ndone. ~{total/1e9:.2f} GB, {len(done)} source clips', flush=True)
    for k, v in sorted(have.items()):
        print(f'  {k}: {v/1e9:.2f} GB', flush=True)


if __name__ == '__main__':
    main()
