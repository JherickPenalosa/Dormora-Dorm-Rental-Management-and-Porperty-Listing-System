
"""Cloudflare Turnstile server-side CAPTCHA verification for Dormora.

Backend File 30 -- install as backend/app/services/captcha_service.py.

This service uses Cloudflare's HTTPS Siteverify API. It never trusts a
frontend-only success indicator and never exposes or logs the private key.
It does not create routes, send email, or change the database.
"""

import ipaddress
import json
import re
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings


_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_MAX_TOKEN_LENGTH = 2048
_MAX_RESPONSE_BYTES = 16_384
_ACTION_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,32}\Z")
_HOST_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}\Z")


class CaptchaUnavailableError(Exception):
    """Siteverify could not be reached or returned an unusable response."""


def verify_turnstile_token(
    token: str,
    *,
    expected_hostname: str,
    expected_action: str,
    client_ip: str | None = None,
) -> bool:
    """Validate one Turnstile token using Cloudflare's Siteverify endpoint.

    Return True only when Cloudflare explicitly accepts the token AND its
    hostname/action match the trusted values supplied by the backend.
    Invalid, expired, and previously used tokens return False.

    Missing configuration raises RuntimeError. Transport/invalid provider
    responses raise CaptchaUnavailableError; callers must fail closed.

    The expected hostname/action must be fixed by the backend, NOT copied
    from a user's request. Only pass client_ip from a trusted IP policy.
    """
    if not isinstance(expected_hostname, str) or not _HOST_PATTERN.fullmatch(
        expected_hostname
    ):
        raise ValueError("expected_hostname must be a hostname without scheme or port.")
    if not isinstance(expected_action, str) or not _ACTION_PATTERN.fullmatch(
        expected_action
    ):
        raise ValueError("expected_action must be a valid Turnstile action label.")

    if client_ip is not None:
        if not isinstance(client_ip, str):
            raise ValueError("client_ip must be an IPv4 or IPv6 address.")
        try:
            client_ip = str(ipaddress.ip_address(client_ip))
        except ValueError:
            raise ValueError("client_ip must be an IPv4 or IPv6 address.") from None

    # Reject bad inputs locally. Do not send malformed client input or expose
    # the secret to the provider unnecessarily.
    if (
        not isinstance(token, str)
        or not (1 <= len(token) <= _MAX_TOKEN_LENGTH)
        or not token.isascii()
        or any(ord(character) <= 32 or ord(character) == 127 for character in token)
    ):
        return False

    secret = settings.require_turnstile_secret()
    form = {"secret": secret, "response": token}
    if client_ip is not None:
        form["remoteip"] = client_ip

    request = Request(
        _SITEVERIFY_URL,
        data=urlencode(form).encode("ascii"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.turnstile_timeout_seconds) as reply:
            if getattr(reply, "status", 200) != 200:
                raise CaptchaUnavailableError("CAPTCHA provider is unavailable.")
            raw_response = reply.read(_MAX_RESPONSE_BYTES + 1)
    except (URLError, OSError, TimeoutError):
        raise CaptchaUnavailableError("CAPTCHA provider is unavailable.") from None

    if len(raw_response) > _MAX_RESPONSE_BYTES:
        raise CaptchaUnavailableError("CAPTCHA provider returned an invalid response.")

    try:
        result = json.loads(raw_response)
    except (ValueError, UnicodeError):
        raise CaptchaUnavailableError("CAPTCHA provider returned an invalid response.") from None

    if not isinstance(result, dict) or type(result.get("success")) is not bool:
        raise CaptchaUnavailableError("CAPTCHA provider returned an invalid response.")

    return (
        result["success"] is True
        and result.get("hostname") == expected_hostname
        and result.get("action") == expected_action
    )
