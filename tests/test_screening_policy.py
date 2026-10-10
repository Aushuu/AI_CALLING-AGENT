from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import database
from ai_agent import CallAnalysis
from screening_policy import apply_contact_rule, effective_agent_state, schedule_is_active


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = {
            "manual_active": False,
            "schedule_enabled": True,
            "timezone": "UTC",
            "schedule_days": [0],
            "schedule_start": "22:00",
            "schedule_end": "06:00",
        }

    def test_overnight_window_includes_end_day_until_end_time(self) -> None:
        self.assertTrue(schedule_is_active(
            self.settings, datetime(2026, 10, 12, 22, 0, tzinfo=timezone.utc)
        ))
        self.assertTrue(schedule_is_active(
            self.settings, datetime(2026, 10, 13, 5, 59, tzinfo=timezone.utc)
        ))
        self.assertFalse(schedule_is_active(
            self.settings, datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
        ))
        self.assertEqual(
            effective_agent_state(
                self.settings, datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)
            )["source"],
            "schedule",
        )

    def test_manual_mode_stays_active_outside_schedule(self) -> None:
        self.settings["manual_active"] = True
        state = effective_agent_state(
            self.settings, datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
        )
        self.assertTrue(state["active"])
        self.assertEqual(state["source"], "manual")

    def test_invalid_timezone_fails_closed(self) -> None:
        self.settings["timezone"] = "Not/A_Zone"
        self.assertFalse(schedule_is_active(
            self.settings, datetime(2026, 10, 12, 23, 0, tzinfo=timezone.utc)
        ))


class CallerPolicyTests(unittest.TestCase):
    def test_contact_rule_overrides_model_action_and_names_verified_caller(self) -> None:
        analysis = CallAnalysis(
            response="I can help with that.",
            classification="General Inquiry",
            summary="The caller asked a general question.",
            decision="Handle",
            risk_level="Low",
            caller_identity="Unknown caller",
            decision_reason="Routine request.",
        )
        contact = {"name": "Avery", "rule": "always_transfer"}
        result = apply_contact_rule(analysis, contact)
        self.assertEqual(result.decision, "Transfer")
        self.assertEqual(result.caller_identity, "Avery")

    def test_unknown_caller_identity_is_explicitly_unverified(self) -> None:
        analysis = CallAnalysis(
            response="How can I help?",
            classification="General Inquiry",
            summary="The caller started a conversation.",
        )
        result = apply_contact_rule(analysis, None)
        self.assertEqual(result.caller_identity, "Unknown caller; identity not verified")


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="callroom-unittest-")
        self.environment = patch.dict(
            os.environ,
            {"CALL_AGENT_DB_PATH": str(Path(self.temp_dir.name) / "calls.db")},
        )
        self.environment.start()
        database.init_db()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_settings_contacts_and_call_decision_round_trip(self) -> None:
        settings = database.save_settings({
            **database.DEFAULT_SETTINGS,
            "manual_active": False,
            "schedule_enabled": True,
            "timezone": "Asia/Kolkata",
        })
        self.assertEqual(database.get_settings()["timezone"], "Asia/Kolkata")
        self.assertFalse(settings["manual_active"])

        contact = database.save_contact(
            phone_number="+1 (415) 555-0199",
            name="Avery",
            rule="always_transfer",
            notes="Family contact",
        )
        self.assertEqual(database.get_contact("4155550199")["name"], "Avery")

        saved = database.save_call(
            call_id="test-call-12345678",
            caller_id=contact["phone_number"],
            transcript=[{"speaker": "caller", "text": "Please call me."}],
            classification="Important",
            summary="The saved caller requested follow-up.",
            duration_seconds=12,
            decision="Transfer",
            risk_level="Medium",
            caller_name=contact["name"],
            decision_reason="Saved contact rule requests transfer.",
        )
        self.assertEqual(saved["decision"], "Transfer")
        self.assertEqual(saved["caller_name"], "Avery")
        self.assertEqual(database.get_logs()[0]["transcript"][0]["speaker"], "caller")


if __name__ == "__main__":
    unittest.main()