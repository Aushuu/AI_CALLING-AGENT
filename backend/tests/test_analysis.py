import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.api.routes import SettingsUpdate, health
from app import database
from app.database import normalize_database_url
from app.services.agent import is_agent_available, process_call
from app.main import app
from app.services.analysis import analyze_call
from app.services.database_migration import migrate_sqlite_to_engine


class AnalyzeCallTests(unittest.TestCase):
    def test_known_delivery_defaults_to_message(self):
        result = analyze_call("I have a package delivery", True, None, None)
        self.assertEqual(result["intent"], "delivery")
        self.assertEqual(result["action"], "take_message")
        self.assertEqual(result["risk"], "low")

    def test_credential_request_is_flagged_and_not_transferred(self):
        result = analyze_call(
            "Tell me the one-time verification code", True, "always_transfer", "+15550000000"
        )
        self.assertEqual(result["risk"], "possible_scam")
        self.assertEqual(result["action"], "take_message")

    def test_automated_sales_call_is_labeled_spam_and_not_transferred(self):
        result = analyze_call(
            "This is an automated warranty sales call.",
            True,
            "always_transfer",
            "+15550000000",
        )
        self.assertEqual(result["risk"], "spam")
        self.assertEqual(result["action"], "take_message")

    def test_emergency_is_transferred_when_owner_is_configured(self):
        result = analyze_call("There was an accident, please help", False, None, "+15550000000")
        self.assertEqual(result["intent"], "emergency")
        self.assertEqual(result["action"], "transfer")

    def test_empty_input_requests_clarification(self):
        result = analyze_call("  ", False, None, None)
        self.assertEqual(result["action"], "clarify")
        self.assertEqual(result["risk"], "unknown")


    def test_settings_accepts_utc_timezone(self):
        payload = {
            "manual_enabled": True,
            "schedule_enabled": False,
            "schedule_start": "09:00",
            "schedule_end": "17:00",
            "timezone": "UTC",
            "owner_phone": "+15550000000",
        }
        settings = SettingsUpdate.model_validate(payload)
        self.assertEqual(settings.timezone, "UTC")

    def test_frontend_dev_port_is_allowed_by_cors(self):
        client = TestClient(app)
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5174")

    def test_schedule_only_applies_on_selected_days(self):
        settings = {
            "manual_enabled": False,
            "schedule_enabled": True,
            "schedule_days": ["Monday", "Tuesday"],
            "schedule_start": "09:00",
            "schedule_end": "17:00",
            "timezone": "UTC",
            "owner_phone": "+15550000000",
        }
        monday = datetime(2026, 10, 12, 12, 0)
        sunday = datetime(2026, 10, 11, 12, 0)
        self.assertTrue(is_agent_available(settings, now=monday))
        self.assertFalse(is_agent_available(settings, now=sunday))

    def test_settings_accepts_explicit_weekday_schedule(self):
        payload = {
            "manual_enabled": False,
            "schedule_enabled": True,
            "schedule_days": ["Monday", "Wednesday", "Friday"],
            "schedule_start": "09:00",
            "schedule_end": "17:00",
            "timezone": "UTC",
            "owner_phone": "+15550000000",
        }
        settings = SettingsUpdate.model_validate(payload)
        self.assertEqual(settings.schedule_days, ["Monday", "Wednesday", "Friday"])

    def test_overnight_schedule_carries_into_following_day(self):
        settings = {
            "manual_enabled": False,
            "schedule_enabled": True,
            "schedule_days": ["Monday"],
            "schedule_start": "22:00",
            "schedule_end": "02:00",
            "timezone": "UTC",
            "owner_phone": "+15550000000",
        }
        tuesday_early = datetime(2026, 10, 13, 1, 0)
        tuesday_at_end = datetime(2026, 10, 13, 2, 0)
        self.assertTrue(is_agent_available(settings, now=tuesday_early))
        self.assertFalse(is_agent_available(settings, now=tuesday_at_end))

    def test_empty_schedule_days_means_never_available(self):
        payload = {
            "manual_enabled": False,
            "schedule_enabled": True,
            "schedule_days": [],
            "schedule_start": "09:00",
            "schedule_end": "17:00",
            "timezone": "UTC",
            "owner_phone": "+15550000000",
        }
        settings = SettingsUpdate.model_validate(payload)
        self.assertEqual(settings.schedule_days, [])

    def test_health_exposes_twilio_webhook_setup_without_secrets(self):
        environment = {"PUBLIC_BASE_URL": "https://calls.example.com"}
        with patch.dict("os.environ", environment, clear=True):
            with patch("app.api.routes.get_settings", return_value={"manual_enabled": True}):
                with patch("app.api.routes.is_agent_available", return_value=True):
                    status = health()

        self.assertEqual(status["twilio_webhook_url"], "https://calls.example.com/api/twilio/voice")
        self.assertFalse(status["twilio_enabled"])
        self.assertFalse(status["inbound_phone_configured"])
        self.assertEqual(
            status["twilio_missing_config"],
            [
                "TWILIO_ACCOUNT_SID",
                "TWILIO_AUTH_TOKEN",
                "INBOUND_PHONE_NUMBER (Twilio Voice number or carrier DID)",
            ],
        )

    def test_health_rejects_local_http_twilio_webhook_url(self):
        environment = {
            "PUBLIC_BASE_URL": "http://127.0.0.1:8000",
            "TWILIO_ACCOUNT_SID": "AC-test",
            "TWILIO_AUTH_TOKEN": "test-token",
        }
        with patch.dict("os.environ", environment, clear=True):
            with patch("app.api.routes.get_settings", return_value={"manual_enabled": True}):
                with patch("app.api.routes.is_agent_available", return_value=True):
                    status = health()

        self.assertFalse(status["twilio_enabled"])
        self.assertFalse(status["twilio_webhook_uses_public_https"])
        self.assertFalse(status["inbound_phone_configured"])
        self.assertIn(
            "PUBLIC_BASE_URL (must be public HTTPS)",
            status["twilio_missing_config"],
        )

    def test_health_requires_inbound_number_even_with_provider_and_https_configured(self):
        environment = {
            "PUBLIC_BASE_URL": "https://calls.example.com",
            "TWILIO_ACCOUNT_SID": "AC-test",
            "TWILIO_AUTH_TOKEN": "test-token",
        }
        with patch.dict("os.environ", environment, clear=True):
            with patch("app.api.routes.get_settings", return_value={"manual_enabled": True}):
                with patch("app.api.routes.is_agent_available", return_value=True):
                    status = health()

        self.assertFalse(status["twilio_enabled"])
        self.assertTrue(status["twilio_webhook_uses_public_https"])
        self.assertFalse(status["inbound_phone_configured"])
        self.assertIn(
            "INBOUND_PHONE_NUMBER (Twilio Voice number or carrier DID)",
            status["twilio_missing_config"],
        )

    def test_render_postgres_url_uses_psycopg_driver(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@db.example.com/calls"),
            "postgresql+psycopg://user:pass@db.example.com/calls",
        )

    def test_render_requires_persistent_database_url(self):
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL must point to persistent PostgreSQL"):
            database.validate_database_configuration(None, True)
        database.validate_database_configuration(None, False)

    def test_database_tables_compile_for_postgresql(self):
        statements = [
            str(CreateTable(table).compile(dialect=postgresql.dialect()))
            for table in database.metadata.sorted_tables
        ]
        self.assertCountEqual(
            [table.name for table in database.metadata.sorted_tables],
            ["calls", "contacts", "settings", "push_subscriptions", "push_delivery_claims"],
        )
        self.assertTrue(any("confidence FLOAT" in statement for statement in statements))
        self.assertTrue(any("call_status VARCHAR(32)" in statement for statement in statements))

    def test_database_adapter_persists_settings_contacts_and_calls(self):
        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "test.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                updated_settings = database.save_settings({"owner_phone": "+15551234567"})
                contact = database.add_contact("Test caller", "+15557654321", "always_message")
                call = {
                    "call_sid": "CA-persistence-test",
                    "caller_phone": contact["phone"],
                    "caller_name": contact["name"],
                    "caller_known": True,
                    "transcript": "I need help with a delivery.",
                    "intent": "delivery",
                    "urgency": "low",
                    "risk": "low",
                    "risk_reasons": [],
                    "confidence": 0.75,
                    "action": "take_message",
                    "summary": "Delivery request.",
                    "provider": "rules",
                    "simulated": False,
                }
                first_call = database.save_call(call)
                updated_call = database.save_call({**call, "summary": "Updated summary."})

                self.assertEqual(updated_settings["owner_phone"], "+15551234567")
                self.assertEqual(database.get_settings()["owner_phone"], "+15551234567")
                self.assertEqual(database.find_contact(contact["phone"])["rule"], "always_message")
                self.assertEqual(updated_call["id"], first_call["id"])
                self.assertEqual(updated_call["summary"], "Updated summary.")
                self.assertEqual(len(database.list_calls()), 1)
                self.assertTrue(database.delete_contact(contact["id"]))
            test_engine.dispose()

    def test_initialize_database_upgrades_existing_calls_table_with_unknown_status(self):
        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "legacy.db")
            with test_engine.begin() as connection:
                connection.execute(database.text(
                    "CREATE TABLE calls ("
                    "id INTEGER PRIMARY KEY, call_sid VARCHAR(64), "
                    "caller_phone VARCHAR(32) NOT NULL, caller_name VARCHAR(80) NOT NULL, "
                    "caller_known INTEGER NOT NULL, transcript TEXT NOT NULL, "
                    "intent VARCHAR(64) NOT NULL, urgency VARCHAR(32) NOT NULL, "
                    "risk VARCHAR(32) NOT NULL, risk_reasons TEXT NOT NULL, "
                    "confidence FLOAT NOT NULL, action VARCHAR(32) NOT NULL, "
                    "summary TEXT NOT NULL, provider VARCHAR(64) NOT NULL, "
                    "simulated INTEGER NOT NULL DEFAULT 1, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                ))
                connection.execute(database.text(
                    "INSERT INTO calls ("
                    "call_sid, caller_phone, caller_name, caller_known, transcript, "
                    "intent, urgency, risk, risk_reasons, confidence, action, summary, "
                    "provider, simulated"
                    ") VALUES ("
                    "'CA-legacy-status', '+15551234567', 'Unknown caller', 0, "
                    "'Old transcript', 'general', 'low', 'unknown', '[]', 0.5, "
                    "'take_message', 'Old call', 'rules', 0)"
                ))

            with patch("app.database.engine", test_engine):
                database.initialize_database()
                migrated_call = database.find_call_by_sid("CA-legacy-status")
                self.assertEqual(migrated_call["call_status"], "unknown")
            test_engine.dispose()

    def test_processed_call_returns_reply_after_database_persistence(self):
        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "agent.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                with patch("app.services.agent.get_settings", return_value={
                    "manual_enabled": True,
                    "owner_phone": "+15551234567",
                }):
                    with patch("app.services.agent.find_contact", return_value=None):
                        result = process_call("+15557654321", "Please call me back.")

                self.assertIn("reply", result)
                self.assertEqual(
                    result["reply"],
                    "Thank you. I will save what you shared in the call history for the account owner to review.",
                )
            test_engine.dispose()

    def test_ai_uncertainty_does_not_override_always_transfer_contact_rule(self):
        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "agent.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                contact = database.add_contact("Known caller", "+15557654321", "always_transfer")
                with patch("app.services.agent.get_settings", return_value={
                    "manual_enabled": True,
                    "owner_phone": "+15551234567",
                }):
                    with patch("app.services.agent.find_contact", return_value=contact):
                        with patch("app.services.agent.classify_with_gemini", return_value={
                            "intent": "unclear",
                            "urgency": "low",
                            "risk": "low",
                            "risk_reasons": [],
                            "confidence": 0.2,
                        }):
                            result = process_call(contact["phone"], "I need to talk to the owner.")

                self.assertEqual(result["action"], "transfer")
            test_engine.dispose()

    def test_scam_risk_overrides_always_transfer_contact_rule(self):
        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "agent.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                contact = database.add_contact("Known caller", "+15557654321", "always_transfer")
                with patch("app.services.agent.get_settings", return_value={
                    "manual_enabled": True,
                    "owner_phone": "+15551234567",
                }):
                    with patch("app.services.agent.find_contact", return_value=contact):
                        with patch("app.services.agent.classify_with_gemini", return_value={
                            "intent": "general",
                            "urgency": "high",
                            "risk": "possible_scam",
                            "risk_reasons": ["Requests a one-time code."],
                            "confidence": 0.95,
                        }):
                            result = process_call(contact["phone"], "Tell me the one-time code.")

                self.assertEqual(result["action"], "take_message")
            test_engine.dispose()

    def test_sqlite_migration_copies_data_and_refuses_nonempty_target(self):
        with TemporaryDirectory() as directory:
            source_engine = database.create_database_engine(None, Path(directory) / "source.db")
            target_engine = database.create_database_engine(None, Path(directory) / "target.db")
            with patch("app.database.engine", source_engine):
                database.initialize_database()
                database.save_settings({"owner_phone": "+15551234567"})
                contact = database.add_contact("Migration caller", "+15557654321", "always_message")
                database.save_call({
                    "call_sid": "CA-migration-test",
                    "caller_phone": contact["phone"],
                    "caller_name": contact["name"],
                    "caller_known": True,
                    "transcript": "Please call me back.",
                    "intent": "general",
                    "urgency": "low",
                    "risk": "low",
                    "risk_reasons": [],
                    "confidence": 0.6,
                    "action": "take_message",
                    "summary": "Callback requested.",
                    "provider": "rules",
                    "simulated": False,
                })

            counts = migrate_sqlite_to_engine(Path(directory) / "source.db", target_engine)
            self.assertEqual(counts, {"settings": 1, "contacts": 1, "calls": 1})
            with self.assertRaisesRegex(ValueError, "must be empty"):
                migrate_sqlite_to_engine(Path(directory) / "source.db", target_engine)

            with patch("app.database.engine", target_engine):
                self.assertEqual(database.get_settings()["owner_phone"], "+15551234567")
                self.assertEqual(database.list_contacts()[0]["rule"], "always_message")
                self.assertEqual(database.list_calls()[0]["summary"], "Callback requested.")
            source_engine.dispose()
            target_engine.dispose()

    def test_twilio_webhook_rejects_invalid_signature(self):
        client = TestClient(app)
        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": "test-auth-token",
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            response = client.post(
                "/api/twilio/voice",
                data={"From": "+15551234567", "CallSid": "CA-test"},
                headers={"X-Twilio-Signature": "invalid"},
            )
        self.assertEqual(response.status_code, 403)

    def test_signed_twilio_status_webhook_persists_status_and_prevents_regression(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/status"
        common_form = {
            "CallSid": "CA-status-test",
            "From": "+15551234567",
            "To": "+15557654321",
        }

        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "status.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                with patch.dict("os.environ", {
                    "TWILIO_AUTH_TOKEN": auth_token,
                    "PUBLIC_BASE_URL": "https://voice.example.com",
                }, clear=True):
                    for status in ("ringing", "completed", "in-progress"):
                        form_data = {**common_form, "CallStatus": status}
                        signature = RequestValidator(auth_token).compute_signature(
                            public_url, form_data
                        )
                        response = client.post(
                            "/api/twilio/status",
                            data=form_data,
                            headers={"X-Twilio-Signature": signature},
                        )
                        self.assertEqual(response.status_code, 204)

                saved_call = database.find_call_by_sid("CA-status-test")
                self.assertEqual(saved_call["caller_phone"], "+15551234567")
                self.assertEqual(saved_call["call_status"], "completed")
                self.assertEqual(saved_call["provider"], "twilio")
                self.assertFalse(saved_call["simulated"])
            test_engine.dispose()

    def test_twilio_status_webhook_rejects_unsupported_status(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/status"
        form_data = {"CallSid": "CA-invalid-status", "CallStatus": "mystery"}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            response = client.post(
                "/api/twilio/status",
                data=form_data,
                headers={"X-Twilio-Signature": signature},
            )

        self.assertEqual(response.status_code, 422)

    def test_signed_twilio_inbound_webhook_returns_gather_xml(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/voice"
        form_data = {"From": "+15551234567", "CallSid": "CA-test"}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)
        settings = {"manual_enabled": True, "owner_phone": ""}

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            with patch("app.api.telephony.get_settings", return_value=settings):
                with patch("app.api.telephony.find_contact", return_value=None):
                    with patch("app.api.telephony.is_agent_available", return_value=True):
                        with patch("app.api.telephony.save_call_start"):
                            response = client.post(
                                "/api/twilio/voice",
                                data=form_data,
                                headers={"X-Twilio-Signature": signature},
                            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("https://voice.example.com/api/twilio/turn", response.text)
        self.assertIn("<Gather", response.text)

    def test_signed_twilio_turn_persists_decision_and_returns_spoken_reply(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/turn"
        form_data = {
            "From": "+15551234567",
            "CallSid": "CA-live-turn-test",
            "SpeechResult": "I have a package delivery for the owner.",
        }
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)
        settings = {"manual_enabled": True, "owner_phone": "+15557654321"}

        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "voice.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                with patch.dict("os.environ", {
                    "TWILIO_AUTH_TOKEN": auth_token,
                    "PUBLIC_BASE_URL": "https://voice.example.com",
                }, clear=True):
                    with patch("app.services.agent.get_settings", return_value=settings):
                        with patch("app.api.telephony.get_settings", return_value=settings):
                            with patch("app.api.telephony.generate_voice_reply", return_value=None):
                                response = client.post(
                                    "/api/twilio/turn",
                                    data=form_data,
                                    headers={"X-Twilio-Signature": signature},
                                )

                persisted_call = database.find_call_by_sid("CA-live-turn-test")
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    "Thank you. I will save what you shared in the call history for the account owner to review.",
                    response.text,
                )
                self.assertIn("<Gather", response.text)
                self.assertEqual(persisted_call["action"], "take_message")
                self.assertIn("Caller: I have a package delivery", persisted_call["transcript"])
                self.assertIn("Agent: Thank you.", persisted_call["transcript"])
                self.assertIn("package delivery", persisted_call["transcript"])
            test_engine.dispose()

    def test_signed_twilio_transfer_fallback_returns_to_message_gather(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/transfer-complete"
        form_data = {"CallSid": "CA-transfer-test", "DialCallStatus": "no-answer"}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            with patch("app.api.telephony.find_call_by_sid", return_value={
                "transcript": "Caller: Please call me about an urgent delivery.\nAgent: Connecting you now.",
            }):
                with patch("app.api.telephony.update_call_transcript") as update_transcript:
                    response = client.post(
                        "/api/twilio/transfer-complete",
                        data=form_data,
                        headers={"X-Twilio-Signature": signature},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertIn("I could not connect you to the account owner", response.text)
        self.assertIn("https://voice.example.com/api/twilio/turn", response.text)
        self.assertIn("<Gather", response.text)
        self.assertIn("do not share passwords or security codes", response.text)
        update_transcript.assert_called_once()

    def test_signed_twilio_transfer_success_hangs_up_agent_flow(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/transfer-complete"
        form_data = {"CallSid": "CA-transfer-success", "DialCallStatus": "completed"}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            response = client.post(
                "/api/twilio/transfer-complete",
                data=form_data,
                headers={"X-Twilio-Signature": signature},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<Hangup", response.text)
        self.assertNotIn("<Gather", response.text)

    def test_twilio_call_handles_multiple_real_speech_turns(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/turn"
        settings = {"manual_enabled": True, "owner_phone": ""}
        call_sid = "CA-multi-turn-test"

        with TemporaryDirectory() as directory:
            test_engine = database.create_database_engine(None, Path(directory) / "multi-turn.db")
            with patch("app.database.engine", test_engine):
                database.initialize_database()
                with patch.dict("os.environ", {
                    "TWILIO_AUTH_TOKEN": auth_token,
                    "PUBLIC_BASE_URL": "https://voice.example.com",
                }, clear=True):
                    with patch("app.services.agent.get_settings", return_value=settings):
                        with patch("app.api.telephony.get_settings", return_value=settings):
                            with patch(
                                "app.api.telephony.generate_voice_reply",
                                side_effect=[
                                    "What time is the delivery?",
                                    "I have noted that for the account owner.",
                                ],
                            ) as generate_reply:
                                first_form = {
                                    "From": "+15551234567",
                                    "CallSid": call_sid,
                                    "SpeechResult": "I have a package delivery.",
                                }
                                first_signature = RequestValidator(auth_token).compute_signature(
                                    public_url, first_form
                                )
                                first_response = client.post(
                                    "/api/twilio/turn",
                                    data=first_form,
                                    headers={"X-Twilio-Signature": first_signature},
                                )

                                second_form = {
                                    **first_form,
                                    "SpeechResult": "It should arrive around three.",
                                }
                                second_signature = RequestValidator(auth_token).compute_signature(
                                    public_url, second_form
                                )
                                second_response = client.post(
                                    "/api/twilio/turn",
                                    data=second_form,
                                    headers={"X-Twilio-Signature": second_signature},
                                )

                saved_call = database.find_call_by_sid(call_sid)
                self.assertEqual(first_response.status_code, 200)
                self.assertEqual(second_response.status_code, 200)
                self.assertIn("What time is the delivery?", first_response.text)
                self.assertIn("I have noted that", second_response.text)
                self.assertIn("<Gather", first_response.text)
                self.assertIn("<Gather", second_response.text)
                self.assertIn("Caller: I have a package delivery.", saved_call["transcript"])
                self.assertIn("Agent: What time is the delivery?", saved_call["transcript"])
                self.assertIn("Caller: It should arrive around three.", saved_call["transcript"])
                generate_reply.assert_called()
            test_engine.dispose()

    def test_empty_twilio_speech_result_reprompts_without_processing_call(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/turn"
        form_data = {"From": "+15551234567", "CallSid": "CA-test", "SpeechResult": "  "}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            with patch("app.api.telephony.process_call") as process_call:
                with patch("app.api.telephony.get_settings", return_value={"owner_phone": ""}):
                    response = client.post(
                        "/api/twilio/turn",
                        data=form_data,
                        headers={"X-Twilio-Signature": signature},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<Gather", response.text)
        self.assertIn("I did not hear you.", response.text)
        process_call.assert_not_called()

    def test_uncertain_twilio_decision_continues_phone_conversation(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/turn"
        form_data = {"From": "+15551234567", "CallSid": "CA-clarify", "SpeechResult": "It is about something important."}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)
        decision = {
            "action": "clarify",
            "reply": "I am not certain I understood. Could you say that another way?",
            "risk": "low",
        }

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            with patch("app.api.telephony.process_call", return_value=decision):
                with patch("app.api.telephony.get_settings", return_value={"owner_phone": ""}):
                    with patch("app.api.telephony.update_call_transcript"):
                        with patch("app.api.telephony.generate_voice_reply", return_value=None):
                            response = client.post(
                                "/api/twilio/turn",
                                data=form_data,
                                headers={"X-Twilio-Signature": signature},
                            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<Gather", response.text)

    def test_twilio_follow_up_appends_caller_turn_to_full_conversation(self):
        client = TestClient(app)
        auth_token = "test-auth-token"
        public_url = "https://voice.example.com/api/twilio/turn"
        form_data = {"From": "+15551234567", "CallSid": "CA-clarify", "SpeechResult": "I need to reschedule tomorrow's appointment."}
        signature = RequestValidator(auth_token).compute_signature(public_url, form_data)

        with patch.dict("os.environ", {
            "TWILIO_AUTH_TOKEN": auth_token,
            "PUBLIC_BASE_URL": "https://voice.example.com",
        }, clear=True):
            with patch("app.api.telephony.find_call_by_sid", return_value={
                "transcript": "It is about something important.",
            }):
                with patch("app.api.telephony.process_call", return_value={
                    "action": "take_message",
                    "reply": "Thank you. I will pass your message to the account owner.",
                    "risk": "low",
                }) as process_call:
                    with patch("app.api.telephony.get_settings", return_value={"owner_phone": ""}):
                        with patch("app.api.telephony.update_call_transcript"):
                            with patch("app.api.telephony.generate_voice_reply", return_value=None):
                                response = client.post(
                                    "/api/twilio/turn",
                                    data=form_data,
                                    headers={"X-Twilio-Signature": signature},
                                )

        self.assertEqual(response.status_code, 200)
        process_call.assert_called_once_with(
            "+15551234567",
            "It is about something important.\nI need to reschedule tomorrow's appointment.",
            call_sid="CA-clarify",
            simulated=False,
        )

    def test_production_api_fails_closed_without_auth_configuration(self):
        client = TestClient(app)
        with patch.dict("os.environ", {"RENDER": "true"}, clear=True):
            health_response = client.get("/api/health")
            settings_response = client.get("/api/settings")

        self.assertTrue(health_response.json()["auth_required"])
        self.assertEqual(settings_response.status_code, 503)

    def test_owner_login_token_authorizes_private_settings(self):
        client = TestClient(app)
        environment = {
            "RENDER": "true",
            "APP_USERNAME": "owner",
            "APP_PASSWORD": "a-long-owner-password-for-test",
            "APP_TOKEN_SECRET": "a-long-test-signing-secret-with-more-than-32-characters",
        }
        with patch.dict("os.environ", environment, clear=True):
            unauthorized = client.get("/api/settings")
            rejected = client.post(
                "/api/auth/login",
                json={"username": "owner", "password": "wrong-password"},
            )
            accepted = client.post(
                "/api/auth/login",
                json={"username": "owner", "password": environment["APP_PASSWORD"]},
            )
            self.assertEqual(rejected.status_code, 401)
            self.assertEqual(accepted.status_code, 200)
            token = accepted.json()["access_token"]
            settings_response = client.get(
                "/api/settings",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(settings_response.status_code, 200)

    def test_infer_caller_identity_from_transcript(self):
        result = analyze_call("Hello, this is Dr. Sarah from Apollo Hospital calling regarding test results.", False, None, None)
        self.assertEqual(result["inferred_caller"], "Dr. Sarah")
        self.assertEqual(result["inferred_organization"], "Apollo Hospital")
        self.assertFalse(result["identity_verified"])
        self.assertIn("Dr. Sarah", result["identity_note"])

    def test_remote_access_scam_flagged(self):
        result = analyze_call("Please install AnyDesk so we can fix your bank account", False, None, None)
        self.assertEqual(result["risk"], "possible_scam")
        self.assertEqual(result["action"], "take_message")

    def test_delivery_agent_personalized_rule(self):
        result = analyze_call("I have a package delivery for you", True, "delivery_agent", None)
        self.assertEqual(result["intent"], "delivery")
        self.assertEqual(result["action"], "take_message")
        self.assertIn("leave the package", result["reply"])

    def test_block_reject_personalized_rule(self):
        result = analyze_call("Hello is anyone there", True, "block_reject", None)
        self.assertEqual(result["action"], "take_message")
        self.assertIn("unavailable", result["reply"])


if __name__ == "__main__":
    unittest.main()

