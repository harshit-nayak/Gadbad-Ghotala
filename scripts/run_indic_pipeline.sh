#!/usr/bin/env bash
# End-to-end: cache features -> baseline eval -> fine-tune head -> eval -> forgetting check.
# Run after build_indic_dataset.py has produced indic_df/manifest.tsv.
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_SYMLINKS_WARNING=1
mkdir -p results_indic

echo "== [1/5] cache frozen-backbone features =="
python cache_features.py --device cuda --batch_size 16

echo "== [2/5] baseline: original model on Indic test =="
python evaluate_indic.py --model_path model.safetensors --split test \
    --out results_indic/eval_baseline.tsv

echo "== [3/5] fine-tune Mamba head on Indic train =="
python finetune_indic.py --device cuda --epochs 40 --batch_size 64 --lr 3e-4

echo "== [4/5] fine-tuned model on Indic test =="
python evaluate_indic.py --model_path model_indic_ft.safetensors --split test \
    --out results_indic/eval_finetuned.tsv

echo "== [5/5] forgetting check: fine-tuned model on ASVspoof5 dev (9000) =="
python evaluate_model.py --model_path model_indic_ft.safetensors \
    --max_samples 9000 --seed 1234 --batch_size 32 --device cuda \
    --scores_out results_indic/asvspoof_after_ft.txt

echo "== done. see results_indic/ =="
