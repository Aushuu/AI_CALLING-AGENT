# Problem Statement Coverage

## Implemented

| Capability | Current implementation |
| --- | --- |
| Manual agent mode | Dashboard toggle controls screening availability. |
| Scheduled agent mode | Weekday schedule, timezone, overnight windows, and explicit empty-day behavior are enforced by the backend. |
| Known and unknown callers | Caller number is normalized and matched against saved contacts; unmatched callers are explicitly treated as unknown. |
| Contact integration | The dashboard offers the browser Device Contacts Picker where supported, with manual entry as fallback. |
| Voice interaction | Twilio answers live inbound calls, gathers each caller speech turn, and speaks a response back over the same telephone call until the caller ends it, hangs up, or is transferred. Caller and agent turns are saved to the transcript. |
| Call lifecycle monitoring | Signed Twilio status callbacks record inbound call progress and terminal outcomes in history; earlier records without callbacks show status as unknown. |
| Caller identification | Matching contact names are announced with a clear warning that the phone number is not independently verified. |
| Spam and fraud screening | Rule-based signals and optional Gemini classification identify spam, suspicious requests, and likely scams. Higher-risk calls are not automatically transferred. |
| Context-aware screening | Decisions combine transcript, caller match, per-contact rule, owner number, urgency, and risk. |
| Intelligent transfer | Important low-risk calls and explicit transfer rules can dial the configured owner. Risk controls override transfer preferences. |
| Agent handling | Suitable calls are summarized and stored for review without requiring an immediate owner interruption. |
| Personalized rules | Contacts support always-screen, always-message, and always-transfer behaviors. |
| Phone-first call handling | The web app is optional and used for configuration/history; live voice is carried by Twilio Voice, not the browser. |
| Persistent production storage | SQLite remains the local default; Render requires a managed PostgreSQL `DATABASE_URL`. A one-time migration command is provided. |
| Owner access control | Production data routes require a signed, expiring owner session; Twilio webhooks require valid Twilio signatures. |

## External Setup Required

- Configure a public HTTPS backend, Twilio credentials, and either a Twilio Voice-number webhook or a BYOC trunk connected to a carrier that can interconnect SIP directly with Twilio.
- For the India-based setup, obtain an Indian DID/SIP trunk through a provider that confirms Twilio BYOC interoperability, then enable no-answer and/or busy forwarding to that DID before carrier voicemail pickup. Confirm provider/carrier compliance requirements and call charges before purchasing.
- Configure Gemini credentials to enable AI-assisted classification; deterministic rules remain the fallback.
- Provision PostgreSQL and run the SQLite migration if existing local records must be retained.

## Platform Boundaries

- A browser cannot silently intercept incoming calls to a device's personal cellular number. This implementation handles those calls only after carrier forwarding to a Twilio number or India DID/SIP trunk connected to Twilio BYOC; it does not replace carrier call-forwarding or voicemail configuration.
- Device contact selection depends on browser support for the Contacts Picker API; manual contact entry remains available when it is unsupported.
- The current Twilio agent answers inbound and carrier-forwarded calls; originating outbound AI calls is not implemented.
- Real Twilio and Gemini integrations have not been verified against live provider accounts in this environment.
