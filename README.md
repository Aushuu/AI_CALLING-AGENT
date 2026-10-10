# Callroom: AI-Powered Personal Call Agent

Callroom is a browser-based call-screening prototype. Speak in the call sandbox, receive a spoken assistant response, and review caller identity, risk, handling/transfer recommendation, transcript, summary, and duration in the SQLite registry. It supports manual and scheduled agent modes, saved caller rules, user preferences, a private dashboard password, and a native dialer handoff.

The microphone conversation is a **voice simulator**, not a cellular call. The transfer link opens the device's native `tel:` dialer for an explicit user tap; placing that outgoing cellular call does not require internet, but carrier service and the device's normal call confirmation still apply. The prototype cannot answer, intercept, bridge, record, or access audio from an incoming cellular call. Android incoming-call screening requires the user to grant the platform's call-screening role, and Android does not expose cellular call audio to an ordinary app. Browser speech recognition requires microphone permission and a supported browser (current Chrome is recommended); the Web Speech service may send recognized audio to the browser vendor for processing.

## Stack

- Python 3.11+
- Flask and Flask-Sock for HTTP and WebSocket transport
- Google Generative AI SDK with Pydantic-validated JSON responses
- SQLite for call history
- SQLite-backed schedule, contacts, and caller-specific screening rules
- IANA time-zone schedules (including overnight windows)
- Device Contact Picker import where supported by the browser
- Explicit native dialer handoff with `tel:` links
- Browser Web Speech recognition and speech synthesis
- Tailwind CSS CDN plus local responsive styles

## Run locally

1. Install Python 3.11 or newer and create a virtual environment.

	```powershell
	py -3.11 -m venv .venv
	.\.venv\Scripts\Activate.ps1
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	```

2. Copy `.env.example` to `.env`. Set `GEMINI_API_KEY` for Gemini responses. The application runs without a key using a deterministic demo fallback; the API key must never be placed in frontend code. Set `DASHBOARD_PASSWORD` to protect the local dashboard if it is reachable by other people.

	```powershell
	Copy-Item .env.example .env
	```

3. Start the development server.

	```powershell
	python app.py
	```

4. Open `http://127.0.0.1:5000` in a supported browser, allow microphone access, enter a caller ID, and choose **Start call**. Use **End call** to save the conversation to `call_agent.db`.
5. Under **Agent rules & schedule**, set the coverage days, time range and time zone, add your cellular number and screening preferences, then save. Add callers with an individual screen, transfer, or agent-handled rule. The device Contact Picker is optional and only imports contacts you select.

Scheduled mode activates the agent when its selected days and local-time interval match. The interval can span midnight. Manual mode stays active regardless of schedule; turning manual mode off leaves scheduled coverage enabled when its window is active.

For reliable microphone access outside localhost, serve the app over HTTPS. Call history is local to the server's SQLite file. Set `CALL_AGENT_DB_PATH` to choose another database location.

Run the policy and persistence checks with `python -m unittest discover -s tests`.

## Render deployment

The repository includes a no-card Render Blueprint in `render.yaml` using the free web-service plan, a health check, generated production secrets, and ephemeral SQLite storage. Create a Blueprint from the repository and provide `GEMINI_API_KEY` when prompted. After deployment, copy the generated `DASHBOARD_PASSWORD` into the team secret manager.

1. In Render, choose **New → Blueprint** and select this repository on `main`. The Blueprint defines the Python build/start commands, health check, free plan, and generated dashboard/session secrets.
2. Enter `GEMINI_API_KEY` directly in Render when prompted. Never commit `.env` or put a key in source control. Production startup fails closed if the dashboard password or unique session secret is missing.
3. Deploy and save the generated `DASHBOARD_PASSWORD` in your team secret manager. Open the HTTPS service URL, sign in, and grant microphone access.
4. Test `/api/health`, then configure a schedule and sample caller rules. Run a short browser call and confirm it appears in the registry.

The free web service has an ephemeral filesystem: its `/tmp/call_agent.db` can be lost on redeploy, restart, or when Render spins the service down after inactivity. Free services may take about a minute to wake after idle. This is appropriate for a temporary hackathon demo, not durable call history. Persistent storage requires a paid disk or changing the app to use a managed database.

## HTTP and WebSocket interface

- `GET /` serves the dashboard.
- `GET /api/health` reports service/database readiness for Render.
- `GET /api/logs` returns the latest call records.
- `GET /api/agent` and `POST /api/agent` read or change manual mode and report effective scheduled/manual state.
- `GET /api/settings` and `PUT /api/settings` read and update schedule, time zone, transfer number and user preferences.
- `GET /api/contacts`, `POST /api/contacts` and `DELETE /api/contacts` manage known callers and per-caller rules.
- `POST /api/save_call` validates and stores a call record; call IDs make retries idempotent.
- `WS /ws/call` accepts `start`, `transcript`, and `end` JSON events, returns validated response, identity, risk, action and transfer metadata, and persists the call on end or unexpected disconnect.

## Hackathon team handoff

- UI: `templates/index.html`, `static/css/style.css`
- API and persistence: `app.py`, `database.py`
- Browser speech and WebSocket client: `static/js/app.js`
- Gemini and response schema: `ai_agent.py`
- Dependencies and deployment: `requirements.txt`, `.env.example`, this README

## Notes

- Gemini model availability depends on the API project and can change over time. The server validates all model output and uses the offline fallback if credentials, provider access, or response validation fail.
- The agent-active toggle is process-local. A single Render worker is configured for the prototype; multiple replicas require shared agent state and a shared production database.
- Schedules and saved contacts are stored in SQLite and are consulted only when the simulator receives a caller ID; on Render's free ephemeral filesystem, they can be lost when the service restarts or spins down. Automatically handling a real incoming cellular call needs a separate native Android app, user-granted call-screening role, device/OEM validation, and supported telephony behavior. The simulator cannot bridge a screened caller to the transfer `tel:` call.
- Model classifications and fallback keyword screening are recommendations, not verified identity or fraud determinations. The interface shows uncertainty and requires a deliberate user action for a transfer; do not use the prototype for emergency screening.
- The dashboard password is a single shared owner credential, not individual user accounts. Use HTTPS, a strong password, and a unique secret key; there is no password reset or retention scheduler. Do not use the prototype for real personal calls.
