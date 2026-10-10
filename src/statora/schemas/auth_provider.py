from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from statora.db.models import AuthProviderType, UserRole


class LdapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_uri: str = Field(description="ldap://host:389 or ldaps://host:636")
    start_tls: bool = False
    verify_tls: bool = True
    # Either search-then-bind (bind_dn + user_search_base) or direct bind (bind_dn_template).
    bind_dn: str | None = None
    bind_password: str | None = Field(default=None, json_schema_extra={"writeOnly": True})
    bind_dn_template: str | None = Field(
        default=None, description="Direct bind, e.g. 'uid={username},ou=users,dc=example,dc=org'"
    )
    user_search_base: str | None = None
    user_filter: str = "(uid={username})"
    username_attr: str = "uid"
    email_attr: str = "mail"
    name_attr: str = "cn"
    # Group lookup: memberOf on the user entry, or a separate search when group_search_base is set.
    group_search_base: str | None = None
    group_filter: str = "(member={user_dn})"
    group_name_attr: str = "cn"

    @model_validator(mode="after")
    def _check_mode(self) -> "LdapConfig":
        if not self.bind_dn_template and not self.user_search_base:
            raise ValueError("Set either bind_dn_template (direct bind) or user_search_base (search + bind)")
        return self


class OidcConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discovery_url: str | None = Field(
        default=None, description="…/.well-known/openid-configuration; leave empty for plain OAuth2"
    )
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str
    client_secret: str | None = Field(default=None, json_schema_extra={"writeOnly": True})
    scopes: str = "openid email profile"
    username_claim: str = "preferred_username"
    email_claim: str = "email"
    name_claim: str = "name"
    groups_claim: str | None = "groups"

    @model_validator(mode="after")
    def _check_endpoints(self) -> "OidcConfig":
        if not self.discovery_url and not (self.authorize_url and self.token_url and self.userinfo_url):
            raise ValueError("Set discovery_url, or authorize_url + token_url + userinfo_url for OAuth2")
        return self


class SamlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idp_metadata_url: str | None = None
    idp_metadata_xml: str | None = None
    idp_entity_id: str | None = None
    idp_sso_url: str | None = None
    idp_x509_cert: str | None = None
    sp_entity_id: str | None = Field(default=None, description="Defaults to the SP metadata URL")
    sp_x509_cert: str | None = None
    sp_private_key: str | None = Field(default=None, json_schema_extra={"writeOnly": True})
    want_assertions_signed: bool = True
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    username_attr: str | None = Field(default=None, description="Attribute for the username; NameID if empty")
    email_attr: str = "email"
    name_attr: str = "displayName"
    groups_attr: str | None = "groups"

    @model_validator(mode="after")
    def _check_idp(self) -> "SamlConfig":
        manual = self.idp_entity_id and self.idp_sso_url and self.idp_x509_cert
        if not (self.idp_metadata_url or self.idp_metadata_xml or manual):
            raise ValueError(
                "Set idp_metadata_url, idp_metadata_xml, or idp_entity_id + idp_sso_url + idp_x509_cert"
            )
        return self


CONFIG_MODELS: dict[AuthProviderType, type[BaseModel]] = {
    AuthProviderType.LDAP: LdapConfig,
    AuthProviderType.OIDC: OidcConfig,
    AuthProviderType.SAML: SamlConfig,
}

SECRET_FIELDS: dict[AuthProviderType, tuple[str, ...]] = {
    AuthProviderType.LDAP: ("bind_password",),
    AuthProviderType.OIDC: ("client_secret",),
    AuthProviderType.SAML: ("sp_private_key",),
}


class AuthProviderBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    group_role_mapping: dict[str, UserRole] = Field(
        default_factory=dict, description="Group name (or DN) to role; the highest matching role wins"
    )
    auto_create_users: bool = True
    default_role: UserRole = UserRole.VIEWER
    button_label: str | None = Field(default=None, max_length=100)


class AuthProviderCreate(AuthProviderBase):
    type: AuthProviderType
    config: dict[str, Any] = Field(description="Type-specific settings; secret fields are write-only")

    @model_validator(mode="after")
    def _validate_config(self) -> "AuthProviderCreate":
        CONFIG_MODELS[self.type].model_validate(self.config)
        return self


class AuthProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    group_role_mapping: dict[str, UserRole] | None = None
    auto_create_users: bool | None = None
    default_role: UserRole | None = None
    button_label: str | None = None
    config: dict[str, Any] | None = Field(
        default=None, description="Replaces the config; omitted secret fields keep their stored value"
    )


class AuthProviderRead(AuthProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: AuthProviderType
    config: dict[str, Any] = Field(description="Secret fields are never returned")
    created_at: datetime
    updated_at: datetime
