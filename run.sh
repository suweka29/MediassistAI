#!/usr/bin/env bash
# MediAssistAI - one-shot setup + launch
set -e
cd "$(dirname "$0")"

echo "== 1/4  Installing Python dependencies =="
pip install -r requirements.txt

echo "== 2/4  Generating synthetic dataset (skips if already present) =="
if [ ! -f data/synthetic_symptom_dataset.csv ]; then
  python data/generate_dataset.py
else
  echo "dataset already exists, skipping"
fi

echo "== 3/4  Training the stacked ensemble (skips if artifacts already present) =="
if [ ! -f ml/artifacts/stacked_model.joblib ]; then
  python ml/train.py
else
  echo "trained model already exists, skipping (delete ml/artifacts/ to retrain)"
fi

echo "== 4/4  Starting the API + chat UI on http://localhost:8000 =="
uvicorn backend.main:app --host 0.0.0.0 --port 8000
