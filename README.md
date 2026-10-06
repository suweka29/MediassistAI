# MediAssistAI

An educational AI symptom-checker chatbot. It takes free-text symptom
descriptions (English, Tanglish/romanised-Tamil, or common Hindi terms),
extracts canonical symptoms, screens for medical emergencies, and runs a
calibrated stacked-ensemble ML model over 50 conditions to produce a
ranked, confidence-scored triage assessment — asking smart follow-up
questions when it isn't confident yet.

**This is a demo trained on synthetic data. It is NOT a medical device and
must never be used for real diagnosis or treatment decisions.**

---

## What's included

```
MediAssistAI/
├── data/
│   ├── disease_profiles.py          50 diseases -> symptom probability profiles
│   ├── generate_dataset.py          synthetic dataset generator
│   └── synthetic_symptom_dataset.csv  10,000 generated patients (pre-built)
├── ml/
│   ├── features.py                  feature engineering (119 symptoms + engineered aggregates)
│   ├── train.py                     trains CatBoost + XGBoost + RandomForest -> LR stacked ensemble
│   ├── predict.py                   inference engine: prediction, confidence, follow-up questions
│   ├── safety.py                    rule-based emergency red-flag screen (runs before any ML call)
│   ├── symptom_nlp.py               multilingual free-text -> symptom extraction (English/Tanglish/Hindi)
│   ├── symptom_knowledge.py         reference knowledge base (kept for reference; not imported by the app)
│   └── artifacts/                   trained model files (pre-built, ready to use)
├── backend/
│   ├── database.py                  SQLite session + message persistence
│   ├── chat_engine.py               glues NLP + safety + ML + DB together for each chat turn
│   └── main.py                      FastAPI app (REST API + serves the frontend)
├── frontend/
│   ├── index.html / style.css / app.js   chat UI (vanilla HTML/CSS/JS, no build step)
├── requirements.txt
└── run.sh                           one-shot setup + launch script
```

## Model performance (already trained, artifacts included)

Trained on a 70/15/15 stratified split of the 10,000-row synthetic dataset:

| metric | value |
|---|---|
| Test accuracy | **94.7%** |
| Top-3 accuracy | **99.3%** |
| Macro F1 | **94.7%** |
| Calibrated log loss | 0.191 |
| Expected calibration error (after temperature scaling) | 0.023 |

Architecture: **CatBoost + XGBoost + RandomForest** base learners feeding a
**Logistic Regression** meta-learner (stacked generalisation), with
**temperature scaling** fitted on a held-out validation split for
well-calibrated probabilities.

## Quick start

Everything is already trained and ready — you only need to install
dependencies and start the server.

```bash
cd MediAssistAI
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in a browser. The chat UI is served
directly by the backend, so there's nothing else to run.

Or use the convenience script, which also re-generates the dataset /
retrains the model if the artifacts are ever deleted:

```bash
cd MediAssistAI
./run.sh
```

### Rebuilding from scratch (optional)

```bash
python data/generate_dataset.py   # regenerate the synthetic dataset
python ml/train.py                # retrain the stacked ensemble (~5-10 min on CPU)
```

## How a conversation works

1. **You describe symptoms** in plain language — e.g. *"I have fever, dry
   cough and loss of smell for 3 days, I'm 28 male"*. The NLP layer pulls
   out canonical symptoms plus age/gender/duration/severity if mentioned,
   including Tanglish and Hindi phrasing and typo-tolerant fuzzy matching.
2. **Safety screen first.** Red-flag combinations (e.g. chest pain +
   sweating + shortness of breath, stroke warning signs, suicidal
   thoughts, severe bleeding, seizures, meningitis signs) short-circuit
   the ML model entirely and return urgent guidance immediately.
3. **If it's not an emergency**, the stacked ensemble scores all 50
   conditions and returns the top 3 with calibrated probabilities.
4. **If confidence is low**, the engine picks the single follow-up
   question with the highest expected information gain (from the top
   5 candidate diseases) and asks it — you can just reply "yes"/"no" or
   click the quick-reply buttons. Up to 3 follow-ups per session.
5. Session state (symptoms mentioned so far, questions already asked,
   demographics) persists in SQLite (`backend/mediassist.db`, created on
   first run) so the conversation stays coherent across turns.

## Login system

The app now requires a user account:

1. Visiting `/` with no saved login redirects to `/login`.
2. **Create account** or **Sign in** on that page (medical-themed hero +
   form). Passwords are hashed with PBKDF2-SHA256 (stdlib `hashlib`,
   200,000 iterations, per-user random salt) — no plaintext storage, no
   extra dependency required.
3. On success, the browser stores a bearer token (`localStorage`) and is
   sent to the chat UI, which attaches `Authorization: Bearer <token>` to
   every API call.
4. Every chat session is tied to the logged-in username — one user can
   never read or continue another user's session (`/api/chat` and
   `/api/session/*` return 404 if the session doesn't belong to the
   caller). "Logout" invalidates the token server-side immediately.

This is intentionally simple (no email verification, no password reset,
one flat `users` table in the same SQLite DB) — appropriate for a local
demo, not a production auth system.

## Precaution / first-aid guidance

Along with the ranked diagnosis, every non-emergency prediction now
includes tailored guidance for the top-matching condition (from
`data/care_advice.py`, covering all 50 diseases):

- **Precautions** — ongoing/preventive steps
- **What you can do now / first aid** — home care for the current episode
- **See a doctor promptly if** — red-flag signs that mean don't wait

This is general, non-prescriptive public-health-style guidance (rest,
hydration, hygiene, when to escalate) — it never states drug names or
doses. It's returned both in the chat message text and as a structured
`care_advice` field in the `/api/chat` response for the frontend card.

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + model metadata |
| POST | `/api/session` | start a session — body: `{age, gender, duration_days, severity}` (all optional) |
| POST | `/api/chat` | send a message — body: `{session_id, message}` |
| GET | `/api/session/{id}/history` | full session state + message log |
| POST | `/api/session/{id}/reset` | reset a session (new patient details, cleared symptoms) |

## Notes / fixes made while completing this project

- The stacked ensemble in `ml/train.py` used a scikit-learn `LogisticRegression`
  argument (`multi_class="multinomial"`) that was removed in current
  scikit-learn versions — removed (multinomial is now the default behavior).
- `ml/symptom_nlp.py`'s tokenizer had a no-op regex substitution that left
  punctuation attached to words, which silently broke multi-word symptom
  matching (e.g. "dry cough," never matched "dry cough" and fell back to a
  weaker fuzzy match on "cough" alone). Fixed the tokenizer to properly
  extract clean word tokens.
- `backend/main.py` now serves `index.html` with content-hash query strings
  on `app.js`/`style.css` (`?v=<hash>`) and sends `Cache-Control: no-cache`
  on `/` and `/static/*`, so browsers always revalidate and pick up the
  latest frontend code after this project is updated — no more stale
  cached JS causing confusing "session not found" errors after an update.
- `frontend/app.js` now recovers automatically if a stored session id is
  no longer known to the backend (e.g. after restarting the server, which
  resets the SQLite session store) — it silently starts a fresh session
  and retries, instead of showing a "session not found" error.
- `ml/predict.py` now includes a small compatibility shim
  (`_patch_sklearn_compat`) that backfills attributes newer scikit-learn
  versions stopped setting on `LogisticRegression` (e.g. `multi_class`,
  removed in scikit-learn 1.8) but older installed versions still read
  during `predict_proba`. Without this, loading a model trained on one
  scikit-learn version and running it on a different installed version
  raises `AttributeError: 'LogisticRegression' object has no attribute
  'multi_class'`. The shim makes the bundled model work across
  scikit-learn 1.4–1.8+ without needing to retrain locally.
- `ml/symptom_knowledge.py` uses a different, non-overlapping symptom
  vocabulary from `data/disease_profiles.py` and isn't imported anywhere in
  the pipeline — it's kept in the project as reference material but the
  live app uses `data/disease_profiles.py` + `ml/symptom_nlp.py`
  consistently throughout.
- Built the entire `backend/` (session orchestration + FastAPI app) and
  `frontend/` (chat UI) from scratch, since only the data/ML core existed
  in the uploaded project.

## Disclaimer

MediAssistAI is trained entirely on **synthetic** data generated from
probabilistic clinical priors, for demonstration purposes. It does not
replace professional medical judgment. In a real emergency, always
contact local emergency services.
