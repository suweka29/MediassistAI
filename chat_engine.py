"""
MediAssistAI - Chat Orchestration
==================================
Glues together:
  * backend.database        (session + message persistence)
  * ml.symptom_nlp           (free-text -> canonical symptoms + demographics)
  * ml.predict.MediAssistEngine (safety screen + stacked ensemble + follow-up)

This is the single entry point the API layer calls for every turn of the
conversation.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import database as db
from ml.symptom_nlp import extract_symptoms
from ml.predict import MediAssistEngine
from data.care_advice import get_care_advice

_engine = None


def get_engine() -> MediAssistEngine:
    """Lazy singleton - the stacked ensemble is ~100MB, load once."""
    global _engine
    if _engine is None:
        _engine = MediAssistEngine()
    return _engine


_YES = {"yes", "y", "yeah", "yep", "ya", "yup", "correct", "true",
        "aama", "amma", "haan", "han", "ha"}
_NO = {"no", "n", "nope", "nah", "not", "false",
       "illa", "illai", "ille", "nahi", "nahin"}

GREETING_MSG = (
    "Hi, I'm MediAssistAI 👋 Tell me what symptoms you're experiencing "
    "(in English, Tanglish, or Hindi is fine) and, if you can, your age, "
    "gender, and how many days you've had them. For example: "
    "\"I have fever, cough and headache for 3 days, I'm 28 male\".\n\n"
    "This is an educational demo, not a real medical diagnosis - if this "
    "is an emergency, contact local emergency services immediately."
)

NO_SYMPTOM_MSG = (
    "I couldn't pick out any specific symptoms from that. Could you "
    "describe how you're feeling? For example: fever, cough, headache, "
    "stomach pain, etc."
)


def start_session(age=35, gender="male", duration_days=3, severity=5,
                  username=None) -> dict:
    sid = db.create_session(age=age, gender=gender,
                            duration_days=duration_days, severity=severity,
                            username=username)
    db.log_message(sid, "assistant", GREETING_MSG)
    return {"session_id": sid, "message": GREETING_MSG}


def _pending_symptom(session: dict):
    lr = session.get("last_result")
    if lr and lr.get("followup_question"):
        return lr["followup_question"].get("symptom")
    return None


def _compose_reply(result: dict) -> str:
    if result["type"] == "emergency":
        icon = "🚨" if result["safety"]["level"] == "emergency" else "⚠️"
        return f"{icon} {result['message']}\n\n{result['disclaimer']}"

    lines = ["Based on what you've told me so far, here's my assessment:", ""]
    for c in result["top_conditions"]:
        pct = round(c["probability"] * 100, 1)
        lines.append(f"• {c['condition']} — {pct}%")
    lines.append("")
    lines.append(f"Confidence: {result['confidence']} "
                 f"({round(result['confidence_score']*100, 1)}%)")
    if "followup_question" in result:
        lines.append("")
        lines.append(result["followup_question"]["question"])

    # -- precaution / home-care / first-aid guidance for the top match ----
    top = result["top_conditions"][0] if result.get("top_conditions") else None
    advice = get_care_advice(top["condition"]) if top else None
    if advice:
        lines.append("")
        lines.append(f"Precautions & self-care for {top['condition']} "
                     f"(most likely match):")
        for p in advice["precautions"]:
            lines.append(f"  • {p}")
        lines.append("")
        lines.append("What you can do now / first aid:")
        for h in advice["home_care"]:
            lines.append(f"  • {h}")
        lines.append("")
        lines.append("See a doctor promptly if:")
        for s in advice["seek_care_if"]:
            lines.append(f"  • {s}")

    lines.append("")
    lines.append(result["disclaimer"])
    return "\n".join(lines)


def handle_message(sid: str, text: str) -> dict:
    """Process one user turn; returns a JSON-serialisable response dict."""
    session = db.get_session(sid)
    if session is None:
        raise ValueError(f"unknown session {sid}")

    db.log_message(sid, "user", text)

    extraction = extract_symptoms(text)
    stripped = text.strip().lower().strip(".!? ")

    pending = _pending_symptom(session)
    new_symptoms = set(extraction["symptoms"])
    negated = set(extraction["negated"])

    # a bare "yes"/"no" answers whatever follow-up question is pending
    if pending and not new_symptoms and not negated:
        if stripped in _YES:
            new_symptoms.add(pending)
        elif stripped in _NO:
            negated.add(pending)

    symptoms = set(session["symptoms"]) | new_symptoms
    asked = set(session["asked"]) | negated | new_symptoms
    if pending:
        asked.add(pending)

    demo = extraction["demographics"]
    age = demo.get("age", session["age"])
    gender = demo.get("gender", session["gender"])
    duration_days = demo.get("duration_days", session["duration_days"])
    severity = demo.get("severity", session["severity"])

    if not symptoms:
        reply = NO_SYMPTOM_MSG
        db.update_session(sid, age=age, gender=gender,
                          duration_days=duration_days, severity=severity)
        db.log_message(sid, "assistant", reply)
        return {"session_id": sid, "type": "clarify", "message": reply,
                "symptoms": [], "top_conditions": [], "confidence": None}

    engine = get_engine()
    result = engine.predict(list(symptoms), age=age, gender=gender,
                            duration_days=duration_days, severity=severity,
                            asked=list(asked))

    followups = session["followups"]
    if result["type"] == "prediction" and "followup_question" in result:
        followups += 1

    db.update_session(sid, age=age, gender=gender,
                      duration_days=duration_days, severity=severity,
                      symptoms=sorted(symptoms), asked=sorted(asked),
                      followups=followups, last_result=result)

    reply = _compose_reply(result)
    db.log_message(sid, "assistant", reply)

    top = result["top_conditions"][0] if result.get("top_conditions") else None
    care_advice = None
    if top:
        advice = get_care_advice(top["condition"])
        if advice:
            care_advice = {"condition": top["condition"], **advice}

    response = {
        "session_id": sid,
        "type": result["type"],
        "message": reply,
        "symptoms": sorted(symptoms),
        "top_conditions": result.get("top_conditions", []),
        "confidence": result.get("confidence"),
        "confidence_score": result.get("confidence_score"),
        "followup_question": result.get("followup_question"),
        "disclaimer": result.get("disclaimer"),
        "care_advice": care_advice,
    }
    if result["type"] == "emergency":
        response["safety"] = result["safety"]
    return response


def reset_session(sid: str, age=35, gender="male", duration_days=3,
                  severity=5) -> dict:
    db.update_session(sid, age=age, gender=gender,
                      duration_days=duration_days, severity=severity,
                      symptoms=[], asked=[], followups=0, last_result=None)
    db.log_message(sid, "assistant", GREETING_MSG)
    return {"session_id": sid, "message": GREETING_MSG}
