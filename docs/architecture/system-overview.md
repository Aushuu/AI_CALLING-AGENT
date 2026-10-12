# AI-Powered Personal Call Agent: System Architecture

## Overview

The **AI-Powered Personal Call Agent** acts as an intelligent intermediary between a phone owner and incoming phone calls. When the owner is busy, unavailable, or in focus hours, the agent answers the call, greets the caller, conducts a natural voice interaction, extracts caller identity, evaluates intent and security risk, applies personalized contact rules, and decides whether to resolve the call autonomously (e.g. taking a message or providing instructions) or intelligently transfer it to the owner.

---

## End-to-End Operational Flow

```mermaid
sequenceDiagram
    autonumber
    actor Caller as Caller
    participant Carrier as Mobile Carrier / Baseband
    participant Agent as Personal Call Agent (Backend)
    participant AI as Gemini & Rules Engine
    actor Owner as Account Owner

    Note over Caller, Carrier: 1. Incoming Call Phase
    Caller->>Carrier: Dials Owner's Mobile Number
    alt Owner Available & Agent Mode OFF
        Carrier->>Owner: Rings Owner's Phone Directly
    else Owner Busy / Agent Mode ON / Focus Schedule
        Carrier->>Agent: Conditional Forwarding (Busy/No Answer) to DID/SIP
        Note over Agent: 2. Caller Recognition Phase
        Agent->>Agent: Lookup Normalized Phone in Contacts
        Agent-->>Caller: Speaks Disclosed Greeting & Gathers Speech
        
        Note over Caller, Agent: 3. Voice Conversation Phase
        loop Multi-turn Speech Screening
            Caller->>Agent: Spoken Turn ("Hello, this is Dr. Sarah from Hospital...")
            Agent->>AI: Analyze Speech: Intent + Risk + Caller Identity
            AI-->>Agent: Evaluation: Intent, Risk Level, Confidence, Action
            alt High Risk / Scam / Spam
                Agent-->>Caller: Politely Deflects & Refuses Credential / Money Transfer
            else Legitimate Call
                Agent-->>Caller: Natural Spoken Follow-up / Confirmation
            end
        end

        Note over Agent, Owner: 4. Judging Focus & Handle / Transfer
        alt High Urgency / Emergency / VIP Contact (Low Risk)
            Agent->>Carrier: Dial Owner Phone (Call Transfer)
            Carrier->>Owner: Cellular Call Transfer
            alt Owner Unanswered / Busy
                Agent-->>Caller: "Owner unavailable; let me take a detailed message."
            end
        else Routine / Delivery / Telemarketing
            Agent-->>Caller: Concludes call & takes structured message
            Agent->>Agent: Persist Call Record, Risk Signals & Transcript
        end
    end
```

---

## Architectural Components

### 1. Telephony & Carrier Layer
- **Native Cellular Calling**: Supports standard GSM/LTE/5G calls using the device's native dialer (`tel:` URI, Android `Intent.ACTION_CALL` / `Intent.ACTION_DIAL`, iOS `UIApplication.open`). **Internet connectivity is not required for cellular calls.**
- **Conditional Call Forwarding**: Callers dial the owner's standard cellular number. The carrier forwards busy/unanswered calls to a dedicated carrier DID or Twilio BYOC SIP trunk.
- **Twilio Voice & TwiML**: Manages real-time bi-directional telephony audio streaming, speech gathering (`<Gather input="speech">`), and speech synthesis (`<Say>`).

### 2. Core Decision Engine (`backend/app/services`)
- **`agent.py`**: Orchestrates state machine across manual toggle, active schedule windows, contact lookup, and risk policies.
- **`analysis.py`**: Fast deterministic classification rules for credential harvesting, payment scams, robocalls, and intent tagging. Extracts self-declared caller identity and evaluates uncertainty.
- **`gemini.py`**: LLM conversational synthesis and nuanced semantic risk reasoning with prompt injection defense.

### 3. Contact & Personalized Rules Layer
- Contacts support customizable rules:
  - `always_screen`: Full conversational screening.
  - `always_message`: Take structured message without ringing owner.
  - `always_transfer`: VIP treatment; rings owner immediately if low risk.
  - `delivery_agent`: Automated package drop-off / courier instructions.
  - `block_reject`: Immediate polite termination.

### 4. Client Dashboard & Native Mobile Bridges
- **PWA Web App**: Installable dashboard with responsive controls, interactive Voice Call Center simulator, and native dialpad.
- **Android Bridge (`mobile/android`)**: Kotlin native implementation utilizing `ContactsContract` and `TelecomManager` for offline telephony.
- **iOS Bridge (`mobile/ios`)**: Swift native implementation utilizing `CNContactStore` and `CoreTelephony`.
