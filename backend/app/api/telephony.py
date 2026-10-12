import os
from urllib.parse import urljoin

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from app.database import (
    CALL_STATUS_ORDER,
    find_call_by_sid,
    find_contact,
    get_settings,
    save_call,
    update_call_status,
    update_call_transcript,
)
from app.services.agent import is_agent_available, process_call
from app.services.gemini import generate_voice_reply
from app.services.push_notifications import send_call_record_notification
from app.api.routes import normalize_phone


router = APIRouter(prefix="/api/twilio")
MAX_SILENCE_REPROMPTS = 2
END_CALL_PHRASES = (
    "goodbye",
    "that's all",
    "that is all",
    "that's it",
    "that is it",
    "nothing else",
    "no thanks",
    "no thank you",
    "end the call",
    "hang up",
)


async def verified_form(request: Request) -> dict[str, str]:
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    public_base_url = os.getenv("PUBLIC_BASE_URL")
    signature = request.headers.get("x-twilio-signature", "")
    if not auth_token or not public_base_url or not signature:
        raise HTTPException(status_code=503, detail="Signed Twilio webhooks are not configured.")

    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    public_url = urljoin(public_base_url.rstrip("/") + "/", request.url.path.lstrip("/"))
    if request.url.query:
        public_url += "?" + request.url.query
    if not RequestValidator(auth_token).validate(public_url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio request signature.")
    return params


def xml_response(response: VoiceResponse) -> Response:
    return Response(str(response), media_type="application/xml")


def gather_for_caller(
    response: VoiceResponse,
    callback_url: str,
    prompt: str = (
        "I am the account owner's AI call assistant. I can take a message. "
        "Please tell me how I can help, and do not share passwords or security codes."
    ),
) -> None:
    gather = response.gather(
        input="speech",
        action=callback_url,
        method="POST",
        timeout=5,
        speech_timeout="auto",
        language="en-US",
        action_on_empty_result=True,
    )
    gather.say(prompt)
    response.say("I could not hear you. Goodbye.")
    response.hangup()


def caller_turns(transcript: str) -> list[str]:
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    caller_lines = [
        line.removeprefix("Caller:").strip()
        for line in lines
        if line.startswith("Caller:")
    ]
    legacy_lines = [
        line for line in lines
        if not line.startswith("Caller:") and not line.startswith("Agent:")
    ]
    return legacy_lines + caller_lines


def append_conversation_turn(transcript: str, speaker: str, words: str) -> str:
    previous = transcript.strip()
    turn = f"{speaker}: {words.strip()}"
    return f"{previous}\n{turn}" if previous else turn


def is_end_call_request(transcript: str) -> bool:
    normalized = " ".join(transcript.lower().split()).strip(" .,!?")
    return any(
        normalized == phrase or normalized.endswith(f" {phrase}")
        for phrase in END_CALL_PHRASES
    )


def save_call_start(params: dict[str, str], status: str = "in-progress") -> None:
    call_sid = params.get("CallSid")
    if not call_sid:
        return
    try:
        caller_phone = normalize_phone(params.get("From", ""))
    except ValueError:
        caller_phone = "Unknown number"
    contact = find_contact(caller_phone) if caller_phone != "Unknown number" else None
    save_call({
        "call_sid": call_sid,
        "caller_phone": caller_phone,
        "caller_name": contact["name"] if contact else "Unknown caller",
        "caller_known": contact is not None,
        "transcript": "",
        "intent": "unknown",
        "urgency": "low",
        "risk": "unknown",
        "risk_reasons": [],
        "confidence": 0.0,
        "action": "take_message",
        "summary": "Call received; waiting for caller speech.",
        "provider": "twilio",
        "simulated": False,
        "call_status": status,
    })


@router.post("/voice")
async def incoming_call(request: Request) -> Response:
    params = await verified_form(request)
    settings = get_settings()
    public_base_url = os.getenv("PUBLIC_BASE_URL")
    if not public_base_url:
        raise HTTPException(status_code=503, detail="PUBLIC_BASE_URL is not configured.")
    response = VoiceResponse()
    save_call_start(params)
    try:
        caller_phone = normalize_phone(params.get("From", ""))
    except ValueError:
        caller_phone = "Unknown number"
    contact = find_contact(caller_phone) if caller_phone != "Unknown number" else None
    if not is_agent_available(settings):
        if settings["owner_phone"]:
            response.say("The call assistant is off. I will try to connect you to the account owner.")
            response.dial(settings["owner_phone"])
        else:
            response.say("The call assistant is currently unavailable. Please try again later.")
            response.hangup()
        return xml_response(response)

    if contact:
        response.say(f"This number matches the saved contact {contact['name']}. The number is not independently verified.")
    callback = urljoin(public_base_url.rstrip("/") + "/", "api/twilio/turn")
    gather_for_caller(
        response,
        callback,
        "I am the account owner's AI call assistant. I can take a message. "
        "What can I help you with? Please do not share passwords or security codes.",
    )
    return xml_response(response)


@router.post("/status", status_code=204)
async def call_status(request: Request, background_tasks: BackgroundTasks) -> Response:
    params = await verified_form(request)
    call_sid = params.get("CallSid", "").strip()
    status = params.get("CallStatus", "").strip().lower()
    if not call_sid:
        raise HTTPException(status_code=422, detail="Twilio CallSid is required.")

    if status not in CALL_STATUS_ORDER or status == "unknown":
        raise HTTPException(status_code=422, detail="Unsupported Twilio call status.")
    updated = update_call_status(call_sid, status)
    if not updated:
        save_call_start(params, status=status)
    if status in {"completed", "busy", "failed", "no-answer", "canceled"}:
        background_tasks.add_task(send_call_record_notification, call_sid)
    return Response(status_code=204)


@router.post("/transfer-complete")
async def transfer_complete(request: Request) -> Response:
    """Resume screening if the owner cannot be reached during a transfer."""
    params = await verified_form(request)
    call_sid = params.get("CallSid", "").strip()
    dial_status = params.get("DialCallStatus", "").strip().lower()
    if not call_sid:
        raise HTTPException(status_code=422, detail="Twilio CallSid is required.")

    response = VoiceResponse()
    if dial_status == "completed":
        response.hangup()
        return xml_response(response)

    call = find_call_by_sid(call_sid)
    transcript = call["transcript"] if call else ""
    recovery_prompt = (
        "I could not connect you to the account owner. I can take a message. "
        "Please tell me what you would like them to know, and do not share passwords or security codes."
    )
    transcript = append_conversation_turn(transcript, "Agent", recovery_prompt)
    update_call_transcript(call_sid, transcript[-4000:])
    callback = urljoin(
        os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/",
        "api/twilio/turn",
    )
    gather_for_caller(response, callback, recovery_prompt)
    return xml_response(response)


@router.post("/turn")
async def caller_turn(request: Request) -> Response:
    params = await verified_form(request)
    transcript = params.get("SpeechResult", "").strip()
    if not transcript:
        response = VoiceResponse()
        silence_value = request.query_params.get("silence", "0")
        silence_count = int(silence_value) if silence_value.isdigit() else 0
        if silence_count >= MAX_SILENCE_REPROMPTS:
            response.say("I still cannot hear you. Goodbye.")
            response.hangup()
            return xml_response(response)
        callback_url = urljoin(
            os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/",
            f"api/twilio/turn?silence={silence_count + 1}",
        )
        gather_for_caller(response, callback_url, "I did not hear you. Please tell me how I can help.")
        return xml_response(response)

    call_sid = params.get("CallSid")
    previous_call = find_call_by_sid(call_sid) if call_sid else None
    previous_transcript = previous_call["transcript"] if previous_call else ""
    full_transcript = append_conversation_turn(previous_transcript, "Caller", transcript)
    caller_transcript = "\n".join(caller_turns(full_transcript))[-1200:]

    try:
        caller_phone = normalize_phone(params.get("From", ""))
    except ValueError:
        caller_phone = "Unknown number"

    result = process_call(caller_phone, caller_transcript, call_sid=call_sid, simulated=False)
    response = VoiceResponse()
    settings = get_settings()
    if is_end_call_request(transcript):
        result["reply"] = "Thank you for calling. Goodbye."
        response.say(result["reply"])
        response.hangup()
    elif result["action"] == "transfer" and settings["owner_phone"]:
        response.say(result["reply"])
        transfer_callback = urljoin(
            os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/",
            "api/twilio/transfer-complete",
        )
        response.dial(
            settings["owner_phone"],
            action=transfer_callback,
            method="POST",
            timeout=20,
        )
        full_transcript = append_conversation_turn(full_transcript, "Agent", result["reply"])
        if call_sid:
            update_call_transcript(call_sid, full_transcript[-4000:])
        return xml_response(response)
    else:
        conversation = append_conversation_turn(full_transcript, "Agent", result["reply"])
        if result["risk"] not in {"spam", "suspicious", "possible_scam"}:
            generated_reply = generate_voice_reply(conversation)
            if generated_reply:
                result["reply"] = generated_reply
        response.say(result["reply"])
        callback = urljoin(os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/", "api/twilio/turn")
        gather_for_caller(response, callback, "Is there anything else I can help the account owner with?")
    conversation = append_conversation_turn(full_transcript, "Agent", result["reply"])
    if call_sid:
        update_call_transcript(call_sid, conversation[-4000:])
    return xml_response(response)
