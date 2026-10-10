from statora.auth.providers import ldap, oidc, saml
from statora.auth.providers.base import AuthError
from statora.db.models import AuthProvider, AuthProviderType

_TESTERS = {
    AuthProviderType.LDAP: ldap.test_connection,
    AuthProviderType.OIDC: oidc.test_connection,
    AuthProviderType.SAML: saml.test_connection,
}


async def test_provider(provider: AuthProvider) -> str:
    try:
        return await _TESTERS[AuthProviderType(provider.type)](provider)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(f"{type(exc).__name__}: {exc}") from exc
