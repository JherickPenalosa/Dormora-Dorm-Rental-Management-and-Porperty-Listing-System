
"""Dormora Backend File 46: Google reCAPTCHA v2 Checkbox server verification.

Install: backend/app/services/recaptcha_v2_service.py (NEW FILE).

This service uses Google's HTTPS Siteverify API. It never trusts a
frontend-only CAPTCHA flag or sends secrets to the browser. It is deliberately
NOT wired into public registration until backend configuration and the React
reCAPTCHA v2 Checkbox widget are added in later files.

A caller creates RecaptchaV2Verifier using a SECRET loaded from private server
configuration and the fixed hostname of the React site (for local development,
"localhost"). The instance is callable and matches File 45's
CaptchaVerifier = Callable[[str], bool] interface.

No third-party Python packages, database writes, emails, or routes.
Official API: https://developers.google.com/recaptcha/docs/verify
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_SITEVERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
_MAX_TOKEN_LENGTH = 8192
_MAX_RESPONSE_BYTES = 16_384
_MAX_TIMEOUT_SECONDS = 30
_HOST_LABEL = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z"
)


class RecaptchaV2ConfigurationError(RuntimeError):
    """The server's private reCAPTCHA settings are missing or invalid."""


class RecaptchaV2UnavailableError(RuntimeError):
    """Google Siteverify did not return a usable response."""


def _validated_hostname(value: str) -> str:
    """Accept only a backend-configured DNS hostname, not a URL or a port."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 253
        or value.endswith(".")
        or not all(
            _HOST_LABEL.fullmatch(label)
            for label in value.split(".")
        )
    ):
        raise RecaptchaV2ConfigurationError(
            "Expected reCAPTCHA hostname is not configured correctly."
        )
    return value.lower()


def _validated_ip(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecaptchaV2ConfigurationError(
            "Trusted client IP is invalid."
        )
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise RecaptchaV2ConfigurationError(
            "Trusted client IP is invalid."
        ) from None


def _usable_token(token: object) -> bool:
    """Reject malformed user tokens without making a provider request."""
    return (
        isinstance(token, str)
        and 1 <= len(token) <= _MAX_TOKEN_LENGTH
        and token.isascii()
        and all(
            33 <= ord(character) <= 126
            for character in token
        )
    )


@dataclass(frozen=True, repr=False)
class RecaptchaV2Verifier:
    """Callable server-side verifier for reCAPTCHA v2 Checkbox tokens.

    secret_key: private SERVER key; never put in React or source control.
    expected_hostname: trusted React hostname only, e.g. "localhost".
    client_ip: optional trusted Request.client.host; NEVER an untrusted header.
    timeout_seconds: bounded HTTPS timeout to avoid hanging registration.

    Build this with keys from validated server configuration in a later file.
    A v3 score-based response is rejected so it cannot masquerade as v2.
    """

    secret_key: str
    expected_hostname: str
    client_ip: str | None = None
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if (
            not isinstance(self.secret_key, str)
            or not self.secret_key
            or len(self.secret_key) > 512
            or not self.secret_key.isascii()
            or any(
                character.isspace()
                for character in self.secret_key
            )
        ):
            raise RecaptchaV2ConfigurationError(
                "Google reCAPTCHA v2 server secret is not configured."
            )

        object.__setattr__(
            self,
            "expected_hostname",
            _validated_hostname(self.expected_hostname),
        )
        object.__setattr__(
            self,
            "client_ip",
            _validated_ip(self.client_ip),
        )

        if (
            type(self.timeout_seconds) is not int
            or not 3 <= self.timeout_seconds <= _MAX_TIMEOUT_SECONDS
        ):
            raise RecaptchaV2ConfigurationError(
                "Google reCAPTCHA request timeout is invalid."
            )

    def __call__(self, token: str) -> bool:
        """Verify a SINGLE token. True only after an accepted HTTPS response.

        Returns False for malformed, expired, reused, incorrectly scoped, or
        otherwise rejected tokens. Raises a safe exception for provider outages,
        invalid provider responses, or invalid server configuration.

        The frontend must acquire a fresh token for each submission; Google's
        verification service enforces the two-minute lifetime and single use.
        """
        if not _usable_token(token):
            return False

        fields = {
            "secret": self.secret_key,
            "response": token,
        }

        if self.client_ip is not None:
            fields["remoteip"] = self.client_ip

        request = Request(
            _SITEVERIFY_URL,
            data=urlencode(fields).encode("ascii"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                if getattr(response, "status", 200) != 200:
                    raise RecaptchaV2UnavailableError(
                        "Google reCAPTCHA verification is unavailable."
                    )

                raw = response.read(
                    _MAX_RESPONSE_BYTES + 1
                )

        except (URLError, OSError, TimeoutError):
            raise RecaptchaV2UnavailableError(
                "Google reCAPTCHA verification is unavailable."
            ) from None

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise RecaptchaV2UnavailableError(
                "Google reCAPTCHA returned an invalid response."
            )

        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError, TypeError):
            raise RecaptchaV2UnavailableError(
                "Google reCAPTCHA returned an invalid response."
            ) from None

        if (
            not isinstance(result, dict)
            or type(result.get("success")) is not bool
        ):
            raise RecaptchaV2UnavailableError(
                "Google reCAPTCHA returned an invalid response."
            )

        if result["success"] is False:
            codes = result.get("error-codes", [])

            if isinstance(codes, list) and any(
                code in {
                    "invalid-input-secret",
                    "missing-input-secret",
                }
                for code in codes
                if isinstance(code, str)
            ):
                raise RecaptchaV2ConfigurationError(
                    "Google reCAPTCHA v2 server credentials were rejected."
                )

            return False

        # A successful v2 Checkbox response contains hostname
        # and challenge_ts. Reject v3-style score/action responses.
        if "score" in result or "action" in result:
            return False

        if result.get("hostname") != self.expected_hostname:
            return False

        challenge_timestamp = result.get("challenge_ts")

        if not isinstance(challenge_timestamp, str):
            return False

        try:
            parsed_timestamp = datetime.fromisoformat(
                challenge_timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            return False

        if parsed_timestamp.tzinfo is None:
            return False

        # Siteverify enforces token expiration and single use.
        return True
