# AI-Powered Personal Call Agent (Problem Statement 01)

An intelligent, phone-first AI personal call assistant that acts as an intermediary between a user and incoming telephone calls. When the user is busy, unavailable, or in focus hours, the agent answers the call over the telephone network, conducts a natural voice interaction, identifies the caller, assesses intent and fraud risk, applies personalized rules, and decides whether to resolve the interaction autonomously or intelligently escalate to the user.

---

## Capabilities Overview

| Requirement | Implementation Details | Status |
| :--- | :--- | :---: |
| **Manual Agent Mode** | Instant toggle on dashboard to switch screening mode ON or OFF manually. | ✅ |
| **Scheduled Agent Mode** | Automated time windows with day-of-week selection, timezone awareness, overnight shifts, and quick preset schedules (Work Hours, Night Shield, 24/7). | ✅ |
| **Known & Unknown Callers** | Phone normalization against address book; treats unsaved numbers with cautious screening and communicates identity uncertainty. | ✅ |
| **Contact Integration** | Integrates device contacts via browser Contacts Picker API, `.vcf` vCard file import, Android `ContactsContract` bridge, and iOS `CNContactStore` bridge. | ✅ |
| **Voice Interaction** | Multi-turn telephone voice interaction via Twilio Programmable Voice (`<Gather input="speech">` + Gemini LLM / TwiML `<Say>`). Includes in-browser Live Voice Call Center with mic Speech-to-Text and Speech Synthesis. | ✅ |
| **Caller Identification** | Identifies saved contacts and extracts self-declared caller identity and organization from caller speech; flags unverified numbers with explicit uncertainty tags. | ✅ |
| **Spam / Fraud Screening** | Multi-class risk assessment (`low`, `spam`, `suspicious`, `possible_scam`). Deflects OTP/2FA theft, remote access scams (AnyDesk, TeamViewer), debt/arrest coercion, and robocalls. | ✅ |
| **Context-Aware Screening** | Combines caller identity, conversation context, urgency levels, owner phone configuration, and active schedules before making routing decisions. | ✅ |
| **Intelligent Transfer** | Escalate important or emergency calls and VIP contacts to the owner's cellular number. High-risk calls are blocked from transfer. Handles transfer fallback to message taking if unanswered. | ✅ |
| **Agent Handling** | Resolves suitable calls autonomously without interrupting the owner (takes structured messages, answers delivery instructions, politely declines telemarketers). | ✅ |
| **Personalized Rules** | Per-contact rules: `always_screen`, `always_message`, `always_transfer` (VIP), `delivery_agent` (doorstep instructions), and `block_reject` (polite decline). | ✅ |
| **Native Cellular Calling** | Dedicated cellular calling interface using the device's native baseband dialer (`tel:` URI, Android `Intent.ACTION_CALL` / `ACTION_DIAL`, iOS `UIApplication.open`). **Zero internet required for cellular calls.** | ✅ |

---

## End-to-End Operational Flow

```
[ Incoming Call ]
        │
        ▼
[ Caller Recognition ] ──► Normalized Phone matched against Contacts
        │                   ├─ Known: Disclose matched contact (unverified CLI notice)
        │                   └─ Unknown: Disclose AI assistant role & ask caller purpose
        ▼
[ Voice Conversation ] ──► Multi-turn speech gathering & natural spoken dialogue
        │
        ▼
[ Judging Focus ]      ──► 1. Intent Detection (Emergency, Delivery, Appointment, Work, Sales)
                           2. Spam/Fraud Risk Scoring (Low, Spam, Suspicious, Possible Scam)
                           3. Identity Extraction & Uncertainty Flagging
                           4. Contact Rule & User Schedule Application
        │
        ▼
[ Handle / Transfer ]  ──► Decision:
                           ├─ High Urgency / VIP (Low Risk) ──► Dial Owner Phone (Transfer)
                           │                                      └─ Unanswered? ──► Take Message
                           ├─ Delivery Carrier               ──► Provide Drop-off Instructions
                           ├─ Spam / Robocall / Scam         ──► Deflect & Refuse Sensitive Data
                           └─ Routine Inquiry                ──► Take Structured Message & Save Record
```

---

## Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes.py            # REST API (health, settings, contacts, calls, demo)
│   │   │   └── telephony.py         # Signed Twilio voice webhooks (/voice, /turn, /status)
│   │   ├── services/
│   │   │   ├── agent.py             # Availability logic, state machine & transfer dispatch
│   │   │   ├── analysis.py          # Intent classification, fraud regex, caller identity inference
│   │   │   ├── auth.py              # Owner JWT authentication & security
│   │   │   ├── gemini.py            # Gemini 2.5 Flash conversational voice & risk classification
│   │   │   └── push_notifications.py# Web Push notification service
│   │   ├── database.py              # SQLAlchemy SQLite & PostgreSQL database adapter
│   │   └── main.py                  # FastAPI application entrypoint
│   ├── tests/
│   │   └── test_analysis.py         # 40 comprehensive unit & integration tests
│   ├── requirements.txt
│   └── run_server.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── App.tsx              # Main dashboard with tabbed navigation
│   │   │   └── routes.tsx           # Route definitions
│   │   ├── components/
│   │   │   ├── CallDecisionPanel.tsx# Judging focus visualizer (Intent, Risk, Confidence)
│   │   │   └── SetupChecklist.tsx   # Carrier & Twilio setup progress checklist
│   │   ├── features/
│   │   │   ├── calls/
│   │   │   │   ├── CallList.tsx     # Call history with risk filters & signals
│   │   │   │   ├── CellularDialpad.tsx # Offline native cellular phone dialpad with DTMF tones
│   │   │   │   └── DemoCallSimulator.tsx # Live Voice & Audio Call Simulator (Mic STT + TTS)
│   │   │   ├── contacts/
│   │   │   │   └── CallerProfile.tsx# Known contacts, personalized rules, vCard import
│   │   │   ├── preferences/
│   │   │   │   └── RuleEditor.tsx   # Manual mode toggle & fraud policy explanation
│   │   │   └── schedules/
│   │   │       └── AgentSchedule.tsx# Scheduled agent mode with presets & day selector
│   │   ├── services/
│   │   │   ├── apiClient.ts         # REST API client with JWT token management
│   │   │   └── soundEffects.ts      # Web Audio API telephone ringtone, DTMF & Speech Synthesis
│   │   └── types/call.ts            # TypeScript interfaces
│   └── package.json
├── mobile/
│   ├── android/app/src/main/
│   │   ├── AndroidManifest.xml      # Telephony permissions (CALL_PHONE, READ_CONTACTS)
│   │   └── java/com/callagent/
│   │       ├── NativeCallBridge.kt  # Android offline cellular dialer bridge (ACTION_CALL/DIAL)
│   │       └── DeviceContactsBridge.kt # ContactsContract query bridge
│   └── ios/CallAgent/
│       ├── NativeCallBridge.swift   # iOS offline cellular dialer bridge (tel: URL scheme)
│       └── DeviceContactsBridge.swift # CNContactStore address book bridge
├── config/
│   └── application.config.ts        # Central TypeScript application configuration
├── deployment/
│   ├── containers/
│   │   ├── Dockerfile               # Multi-stage production container build
│   │   ├── Dockerfile.frontend      # Development container
│   │   └── compose.yaml             # Docker Compose full-stack specification
│   └── infrastructure/
│       └── deployment.yaml          # Kubernetes Deployment & Service manifests
├── docs/
│   ├── api/openapi.yaml             # OpenAPI 3.0 specification
│   ├── architecture/system-overview.md # System architecture & Mermaid sequence diagrams
│   └── security/privacy-and-safety.md  # Threat model, prompt injection defense & safety rules
└── README.md
```

---

## Quickstart & Local Development

### 1. Backend Service

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_server.py
```

The FastAPI backend will start at `http://127.0.0.1:8000`.

### 2. Frontend Dashboard

```powershell
cd frontend
npm install
npm run dev
```

The React dashboard will start at `http://localhost:5173`.

### 3. Running Test Suite

```powershell
cd backend
.venv\Scripts\activate
python -m unittest discover tests -v
```

All 40 unit and integration tests will execute and validate the rules engine, database adapter, schedule calculation, caller identification, personalized contact rules, and Twilio webhooks.

### 4. Production Build

```powershell
cd frontend
npm run build
```

---

## Native Cellular Telephony & Carrier Integration

1. **Native Cellular Dialing**:
   - The dashboard includes a dedicated **Cellular Dialer** with DTMF audio touch tones.
   - Dialing opens your phone's native phone dialer (`tel:<number>`) and initiates a cellular call through your mobile carrier SIM.
   - **Internet connectivity is not required for the actual cellular call.**

2. **Conditional Forwarding**:
   - Dial these MMI codes on your phone to forward unanswered calls to the agent's carrier DID:
     - `*67*<DID>#` (Forward when Busy / Call Rejected)
     - `*61*<DID>#` (Forward when Unanswered / No Pick-up)
     - `*62*<DID>#` (Forward when Unreachable / Out of Coverage)
   - When you are unavailable, the carrier automatically forwards the live call to the agent.
