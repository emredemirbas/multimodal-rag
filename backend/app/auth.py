from __future__ import annotations

from secrets import compare_digest
from typing import Mapping, Protocol

from pydantic import ValidationError

from .models import AuthenticatedPrincipal


class AuthenticationError(Exception):
    """Safe authentication failure exposed as a stable API error."""

    def __init__(
        self,
        detail: str = "Valid authentication credentials are required.",
        *,
        code: str = "authentication_required",
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class Authenticator(Protocol):
    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedPrincipal: ...


def _bearer_token(headers: Mapping[str, str]) -> str:
    authorization = headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError()
    return token.strip()


class DevelopmentAuthenticator:
    """Single-principal local authenticator; never valid in production."""

    def __init__(self, *, token: str, subject: str, tenant_id: str) -> None:
        if len(token) < 16:
            raise ValueError(
                "development authentication token must contain at least 16 characters"
            )
        self._token = token
        self._principal = AuthenticatedPrincipal(
            provider="development",
            subject=subject,
            tenant_id=tenant_id,
        )

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedPrincipal:
        token = _bearer_token(headers)
        if not compare_digest(token, self._token):
            raise AuthenticationError(code="invalid_authentication")
        return self._principal


class TrustedProxyAuthenticator:
    """Trust identity headers only after authenticating the upstream proxy."""

    secret_header = "x-trusted-proxy-secret"
    subject_header = "x-authenticated-subject"
    tenant_header = "x-authenticated-tenant"

    def __init__(self, *, shared_secret: str) -> None:
        if len(shared_secret) < 16:
            raise ValueError("trusted proxy secret must contain at least 16 characters")
        self._shared_secret = shared_secret

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedPrincipal:
        supplied_secret = headers.get(self.secret_header, "")
        if not supplied_secret or not compare_digest(supplied_secret, self._shared_secret):
            raise AuthenticationError(code="invalid_authentication")

        try:
            return AuthenticatedPrincipal(
                provider="trusted_proxy",
                subject=headers.get(self.subject_header, ""),
                tenant_id=headers.get(self.tenant_header, ""),
            )
        except ValidationError as exc:
            raise AuthenticationError(
                "The trusted proxy did not provide a valid identity.",
                code="invalid_authentication",
            ) from exc
