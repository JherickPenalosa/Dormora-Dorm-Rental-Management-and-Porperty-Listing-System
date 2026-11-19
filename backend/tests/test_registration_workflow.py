
"""Offline-safe workflow behavior tests for Dormora registration + email OTP.

Backend File 24
Destination: backend/tests/test_registration_workflow.py
Run from backend/: python -m unittest discover -s tests -p "test_registration_workflow.py" -v

Uses mocks for every operation that writes to PostgreSQL or sends SMTP email.
Importing the existing services may reflect PostgreSQL table metadata, so the
local database should be reachable. Tests never create real accounts/OTPs or
send email, and they do not need your real OTP or SMTP secrets.
"""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.schemas.auth import RegisterRequest
from app.services import registration_workflow as workflow
from app.services.email_service import EmailDeliveryError
from app.services.registration import (
    DuplicateRegistrationError,
    RegistrationResult,
)


class RegistrationWorkflowTests(unittest.TestCase):
    """Confirm the workflow's successful and fail-closed control paths."""

    def setUp(self) -> None:
        # A complete, fictional registration request that passes File 12.
        self.payload = RegisterRequest(
            username="test_renter",
            email="TEST@example.com",
            password="Example!234567",
            role="renter",
            id_number="1234-5678",
            first_name="Juan",
            family_name="Dela Cruz",
            birthdate="2002-06-15",
            street="Purok 1",
            barangay="Poblacion",
            city="Cabadbaran",
            province="Agusan del Norte",
            country="Philippines",
            zip_code="8605",
        )
        self.registration = RegistrationResult(
            user_id=999,
            username="test_renter",
            email="test@example.com",
            role="renter",
            account_status="pending_verification",
        )
        self.issued_otp = SimpleNamespace(otp_id=501)

        # Replace the SETTINGS VARIABLE in the workflow, not methods on a
        # Pydantic Settings instance (Pydantic rejects that form of patching).
        self.fake_settings = SimpleNamespace(
            require_otp_hmac_key=Mock(return_value=b"k" * 32),
            require_smtp_configuration=Mock(return_value=None),
        )

        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(
            patch.object(workflow, "settings", self.fake_settings)
        )
        self.register = self.patches.enter_context(
            patch.object(
                workflow, "register_user", return_value=self.registration
            )
        )
        self.issue = self.patches.enter_context(
            patch.object(
                workflow, "issue_registration_otp", return_value=self.issued_otp
            )
        )
        self.send = self.patches.enter_context(
            patch.object(workflow, "send_registration_otp_email")
        )
        self.mark_sent = self.patches.enter_context(
            patch.object(workflow, "mark_otp_sent", return_value=True)
        )
        self.mark_failed = self.patches.enter_context(
            patch.object(workflow, "mark_otp_failed", return_value=True)
        )

    def test_success_keeps_account_pending_and_marks_otp_sent(self) -> None:
        result = workflow.register_with_email_otp(self.payload)

        self.assertEqual(result, self.registration)
        self.assertEqual(result.account_status, "pending_verification")
        self.register.assert_called_once_with(self.payload)
        self.issue.assert_called_once_with(999)
        self.send.assert_called_once_with(self.issued_otp)
        self.mark_sent.assert_called_once_with(501)
        self.mark_failed.assert_not_called()
        self.assertNotIn(self.payload.password.get_secret_value(), repr(result))

    def test_missing_hmac_key_prevents_registration(self) -> None:
        self.fake_settings.require_otp_hmac_key.side_effect = RuntimeError(
            "Test: OTP key unavailable"
        )
        with self.assertRaises(RuntimeError):
            workflow.register_with_email_otp(self.payload)

        self.register.assert_not_called()
        self.issue.assert_not_called()
        self.send.assert_not_called()
        self.fake_settings.require_smtp_configuration.assert_not_called()

    def test_missing_smtp_config_prevents_registration(self) -> None:
        self.fake_settings.require_smtp_configuration.side_effect = RuntimeError(
            "Test: SMTP unavailable"
        )
        with self.assertRaises(RuntimeError):
            workflow.register_with_email_otp(self.payload)

        self.register.assert_not_called()
        self.issue.assert_not_called()
        self.send.assert_not_called()

    def test_duplicate_registration_never_issues_otp(self) -> None:
        self.register.side_effect = DuplicateRegistrationError(
            "Test: Duplicate account"
        )
        with self.assertRaises(DuplicateRegistrationError):
            workflow.register_with_email_otp(self.payload)

        self.issue.assert_not_called()
        self.send.assert_not_called()
        self.mark_sent.assert_not_called()

    def test_otp_issuance_failure_never_sends_email(self) -> None:
        self.issue.side_effect = RuntimeError("Test: OTP issuance failed")
        with self.assertRaises(RuntimeError):
            workflow.register_with_email_otp(self.payload)

        self.register.assert_called_once_with(self.payload)
        self.send.assert_not_called()
        self.mark_sent.assert_not_called()

    def test_email_send_failure_invalidates_pending_otp(self) -> None:
        self.send.side_effect = EmailDeliveryError("Test: Email rejected")
        with self.assertRaises(workflow.RegistrationEmailDeliveryError):
            workflow.register_with_email_otp(self.payload)

        self.mark_failed.assert_called_once_with(501)
        self.mark_sent.assert_not_called()

    def test_unconfirmed_delivery_status_never_reports_success(self) -> None:
        self.mark_sent.return_value = False
        with self.assertRaises(workflow.RegistrationDeliveryStateError):
            workflow.register_with_email_otp(self.payload)

        self.send.assert_called_once_with(self.issued_otp)
        self.mark_sent.assert_called_once_with(501)


if __name__ == "__main__":
    unittest.main()
