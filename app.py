"""Flask application and WebSocket endpoint for the call-agent demo."""

from __future__ import annotations

import json
import hmac
import logging
import os
import re
import time
import uuid
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from flask_sock import Sock

import database
from ai_agent import CallAnalysis, analyze_call
from screening_policy import apply_contact_rule, effective_agent_state


load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "local-development-only-change-me")
app.config["DASHBOARD_PASSWORD"] = os.getenv("DASHBOARD_PASSWORD", "")
_is_production = os.getenv("APP_ENV", "development").lower() == "production" or os.getenv("RENDER") == "true"
_session_secret = str(app.config["SECRET_KEY"])
if _is_production and (
    not app.config["DASHBOARD_PASSWORD"]
    or len(_session_secret) < 32
    or _session_secret in {
        "local-development-only-change-me",
        "replace-with-a-long-random-secret",
    }
):
    raise RuntimeError("Production requires DASHBOARD_PASSWORD and a unique FLASK_SECRET_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _is_production
sock = Sock(app)
_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,80}$")
_ALLOWED_SPEAKERS = {"caller", "agent"}
_PHONE_PATTERN = re.compile(r"^\+?[0-9().\-\s]{7,40}$")
_CLOCK_PATTERN = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

database.init_db()


@app.after_request
def add_security_headers(response: Any) -> Any:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "microphone=(self)")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.before_request
def require_dashboard_login() -> Any:
    password = app.config.get("DASHBOARD_PASSWORD", "")
    if not password or request.endpoint in {"static", "login", "logout", "health"}:
        return None
    if session.get("authenticated") is True:
        return None
    if request.path == "/" and request.method == "GET":
        return render_template("login.html")
    return jsonify({"error": "Sign in to access the personal call dashboard."}), 401


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/health")
def health() -> Any:
    database.get_settings()
    return jsonify({"status": "ok"})


@app.post("/api/login")
def login() -> Any:
    password = app.config.get("DASHBOARD_PASSWORD", "")
    if not password:
        session["authenticated"] = True
        return jsonify({"authenticated": True})
    payload = request.get_json(silent=True)
    supplied = str(payload.get("password", "")) if isinstance(payload, dict) else ""
    if not hmac.compare_digest(supplied.encode("utf-8"), password.encode("utf-8")):
        return jsonify({"error": "Password did not match."}), 401
    session.clear()
    session["authenticated"] = True
    return jsonify({"authenticated": True})


@app.post("/api/logout")
def logout() -> Any:
    session.clear()
    return jsonify({"authenticated": False})


@app.get("/api/logs")
def list_logs() -> Any:
    try:
        return jsonify({"logs": database.get_logs()})
    except (OSError, ValueError):
        logger.exception("Unable to read call registry")
        return jsonify({"error": "Call history is temporarily unavailable."}), 500


@app.get("/api/agent")
def get_agent_status() -> Any:
    settings = database.get_settings()
    return jsonify(effective_agent_state(settings))


@app.post("/api/agent")
def set_agent_status() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("active"), bool):
        return jsonify({"error": "Provide a boolean active value."}), 400
    settings = database.save_settings({**database.get_settings(), "manual_active": payload["active"]})
    return jsonify(effective_agent_state(settings))


@app.get("/api/settings")
def get_settings() -> Any:
    settings = database.get_settings()
    return jsonify({"settings": settings, "agent": effective_agent_state(settings)})


@app.put("/api/settings")
def update_settings() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    settings = {**database.get_settings(), **payload}
    if not isinstance(settings.get("manual_active"), bool) or not isinstance(settings.get("schedule_enabled"), bool):
        return jsonify({"error": "Agent mode values must be boolean."}), 400
    try:
        ZoneInfo(str(settings.get("timezone", "UTC")))
    except (ZoneInfoNotFoundError, ValueError):
        return jsonify({"error": "Choose a valid IANA time zone."}), 400
    days = settings.get("schedule_days")
    if (
        not isinstance(days, list)
        or not days
        or any(type(day) is not int or day < 0 or day > 6 for day in days)
        or len(set(days)) != len(days)
    ):
        return jsonify({"error": "Select at least one valid schedule day."}), 400
    for key in ("schedule_start", "schedule_end"):
        if not isinstance(settings.get(key), str) or not _CLOCK_PATTERN.fullmatch(settings[key]):
            return jsonify({"error": "Schedule times must use 24-hour HH:MM format."}), 400
    transfer_number = str(settings.get("transfer_number", "")).strip()
    if transfer_number and (
        not _PHONE_PATTERN.fullmatch(transfer_number)
        or len(database.normalize_phone(transfer_number)) < 7
    ):
        return jsonify({"error": "Transfer number must be a valid phone number."}), 400
    preferences = str(settings.get("preferences", "")).strip()
    if len(preferences) > 1200:
        return jsonify({"error": "Personal preferences must be 1,200 characters or fewer."}), 400
    settings["timezone"] = str(settings["timezone"])
    settings["schedule_days"] = sorted(set(days))
    settings["transfer_number"] = transfer_number
    settings["preferences"] = preferences
    saved = database.save_settings(settings)
    return jsonify({"settings": saved, "agent": effective_agent_state(saved)})


@app.route("/api/contacts", methods=["GET", "POST", "DELETE"])
def contacts_endpoint() -> Any:
    if request.method == "GET":
        return jsonify({"contacts": database.get_contacts()})
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    if request.method == "DELETE":
        phone_number = str(payload.get("phone_number", ""))
        if database.delete_contact(phone_number):
            return jsonify({"deleted": True})
        return jsonify({"error": "Contact was not found."}), 404
    try:
        contact = database.save_contact(
            phone_number=str(payload.get("phone_number", "")),
            name=str(payload.get("name", "")),
            rule=str(payload.get("rule", "screen")),
            notes=str(payload.get("notes", "")),
        )
        return jsonify({"contact": contact}), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


def _normalize_transcript(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("Transcript must be a list of messages")
    normalized: list[dict[str, str]] = []
    for message in value[-200:]:
        if not isinstance(message, dict):
            continue
        speaker = str(message.get("speaker", "caller"))
        text = str(message.get("text", "")).strip()
        if speaker not in _ALLOWED_SPEAKERS or not text:
            continue
        normalized.append({"speaker": speaker, "text": text[:2000]})
    return normalized


def _save_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    call_id = str(payload.get("call_id", ""))
    caller_id = str(payload.get("caller_id", "")).strip()
    if not _CALL_ID_PATTERN.fullmatch(call_id):
        raise ValueError("Call ID is invalid")
    if not caller_id or len(caller_id) > 80:
        raise ValueError("Caller ID must contain between 1 and 80 characters")
    transcript = _normalize_transcript(payload.get("transcript", []))
    classification = payload.get("classification", "General Inquiry")
    summary = str(payload.get("summary", "Call ended."))[:500]
    try:
        duration_seconds = max(0, min(int(payload.get("duration_seconds", 0)), 86_400))
    except (TypeError, ValueError) as error:
        raise ValueError("Duration must be a whole number of seconds") from error
    analysis = CallAnalysis(
        response="Call ended.",
        classification=classification,
        summary=summary,
        decision=payload.get("decision", "Handle"),
        risk_level=payload.get("risk_level", "Medium"),
        caller_identity=str(payload.get("caller_name", "Unknown caller"))[:100] or "Unknown caller",
        decision_reason=str(payload.get("decision_reason", "Call completed."))[:300] or "Call completed.",
    )
    return database.save_call(
        call_id=call_id,
        caller_id=caller_id,
        transcript=transcript,
        classification=analysis.classification,
        summary=analysis.summary,
        duration_seconds=duration_seconds,
        decision=analysis.decision,
        risk_level=analysis.risk_level,
        caller_name=analysis.caller_identity,
        decision_reason=analysis.decision_reason,
    )


@app.post("/api/save_call")
def save_call_endpoint() -> Any:
    try:
        saved = _save_payload(request.get_json(silent=True))
        return jsonify({"call": saved}), 201
    except (ValueError, TypeError) as error:
        return jsonify({"error": str(error)}), 400
    except (OSError, RuntimeError):
        logger.exception("Unable to save call")
        return jsonify({"error": "Call could not be saved."}), 500


def _send(socket: Any, payload: dict[str, Any]) -> bool:
    try:
        socket.send(json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:
        return False


@sock.route("/ws/call")
def call_socket(socket: Any) -> None:
    call_id = str(uuid.uuid4())
    caller_id = "Unknown caller"
    caller = None
    settings = database.get_settings()
    transcript: list[dict[str, str]] = []
    started_at: float | None = None
    final_analysis = CallAnalysis(
        response="Call ended.",
        classification="General Inquiry",
        summary="The call ended without a message.",
        decision="Handle",
        risk_level="Low",
        caller_identity="Unknown caller",
        decision_reason="No caller message was received.",
    )
    persisted = False
    _send(socket, {"type": "ready", "call_id": call_id})

    try:
        while True:
            raw_message = socket.receive()
            if raw_message is None:
                break
            try:
                message = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                _send(socket, {"type": "error", "message": "Message must be valid JSON."})
                continue
            if not isinstance(message, dict):
                _send(socket, {"type": "error", "message": "Message must be a JSON object."})
                continue

            event_type = message.get("type")
            if event_type == "start":
                candidate_caller = str(message.get("caller_id", "")).strip()
                if not candidate_caller or len(candidate_caller) > 80:
                    _send(socket, {"type": "error", "message": "Enter a caller ID of 1 to 80 characters."})
                    continue
                caller_id = candidate_caller
                caller = database.get_contact(caller_id)
                started_at = time.monotonic()
                _send(socket, {"type": "started", "call_id": call_id})
                continue

            if event_type == "transcript":
                text = str(message.get("text", "")).strip()
                if not text:
                    continue
                text = text[:1000]
                transcript.append({"speaker": "caller", "text": text})
                transcript = transcript[-200:]
                settings = database.get_settings()
                agent_state = effective_agent_state(settings)
                if not agent_state["active"]:
                    final_analysis = CallAnalysis(
                        response="I cannot screen this call while the agent is offline. Please contact the person directly.",
                        classification="General Inquiry",
                        summary="The caller left a message while the agent was offline.",
                        decision="Review",
                        risk_level="Medium",
                        caller_identity=caller["name"] if caller else "Unknown caller; identity not verified",
                        decision_reason="Agent mode is offline outside the configured schedule.",
                    )
                else:
                    context = {
                        "caller_name": caller["name"] if caller else "Unknown caller; identity not verified",
                        "caller_rule": caller["rule"] if caller else "No saved caller rule",
                        "caller_notes": caller["notes"] if caller else "",
                        "preferences": settings.get("preferences", ""),
                    }
                    final_analysis = apply_contact_rule(
                        analyze_call(transcript, caller_id, context), caller
                    )
                transcript.append({"speaker": "agent", "text": final_analysis.response})
                _send(
                    socket,
                    {
                        "type": "response",
                        "response": final_analysis.response,
                        "classification": final_analysis.classification,
                        "summary": final_analysis.summary,
                        "decision": final_analysis.decision,
                        "risk_level": final_analysis.risk_level,
                        "caller_identity": final_analysis.caller_identity,
                        "decision_reason": final_analysis.decision_reason,
                        "transfer_number": settings.get("transfer_number", ""),
                        "agent_source": agent_state["source"],
                    },
                )
                continue

            if event_type == "end":
                duration_seconds = max(0, int(time.monotonic() - (started_at or time.monotonic())))
                try:
                    saved = database.save_call(
                        call_id=call_id,
                        caller_id=caller_id,
                        transcript=transcript,
                        classification=final_analysis.classification,
                        summary=final_analysis.summary,
                        duration_seconds=duration_seconds,
                        decision=final_analysis.decision,
                        risk_level=final_analysis.risk_level,
                        caller_name=caller["name"] if caller else "Unknown caller",
                        decision_reason=final_analysis.decision_reason,
                    )
                    persisted = True
                    _send(socket, {"type": "call_saved", "call": saved})
                except (OSError, RuntimeError):
                    logger.exception("Unable to persist completed WebSocket call")
                    _send(socket, {"type": "error", "message": "Call ended but could not be saved."})
                break

            _send(socket, {"type": "error", "message": "Unknown event type."})
    except Exception:
        logger.exception("Call WebSocket disconnected unexpectedly")
    finally:
        if transcript and not persisted:
            try:
                database.save_call(
                    call_id=call_id,
                    caller_id=caller_id,
                    transcript=transcript,
                    classification=final_analysis.classification,
                    summary=final_analysis.summary,
                    duration_seconds=max(0, int(time.monotonic() - (started_at or time.monotonic()))),
                    decision=final_analysis.decision,
                    risk_level=final_analysis.risk_level,
                    caller_name=caller["name"] if caller else "Unknown caller",
                    decision_reason=final_analysis.decision_reason,
                )
            except Exception:
                logger.exception("Unable to save interrupted call")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        threaded=True,
    )