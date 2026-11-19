"""OAuth state in the SAME database, separate additive migration metadata.

Only SHA256 digests of random codes/tokens are persisted. Clinical table
fingerprints and clinical data are unchanged by this additive migration.
"""
from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class OAuthBase(DeclarativeBase):
    pass

class OAuthClient(OAuthBase):
    __tablename__='assistant_oauth_clients'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    name: Mapped[str]=mapped_column(String(100))
    redirects: Mapped[list]=mapped_column(JSON)

class OAuthCode(OAuthBase):
    __tablename__='assistant_oauth_codes'
    digest: Mapped[str]=mapped_column(String(64),primary_key=True)
    client_id: Mapped[str]=mapped_column(String(64))
    user_id: Mapped[str]=mapped_column(String(36))
    redirect_uri: Mapped[str]=mapped_column(Text)
    challenge: Mapped[str]=mapped_column(String(43))
    resource: Mapped[str]=mapped_column(Text)
    scope: Mapped[str]=mapped_column(String(100))
    credential_version: Mapped[str]=mapped_column(String(64))
    mfa_verified: Mapped[bool]=mapped_column(Boolean)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool]=mapped_column(Boolean,default=False)

class OAuthGrant(OAuthBase):
    __tablename__='assistant_oauth_grants'
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id: Mapped[str]=mapped_column(String(36),index=True)
    client_id: Mapped[str]=mapped_column(String(64))
    resource: Mapped[str]=mapped_column(Text)
    scope: Mapped[str]=mapped_column(String(100))
    credential_version: Mapped[str]=mapped_column(String(64))
    mfa_verified: Mapped[bool]=mapped_column(Boolean)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool]=mapped_column(Boolean,default=False)

class OAuthToken(OAuthBase):
    __tablename__='assistant_oauth_tokens'
    digest: Mapped[str]=mapped_column(String(64),primary_key=True)
    grant_id: Mapped[str]=mapped_column(String(36),index=True)
    kind: Mapped[str]=mapped_column(String(10))
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool]=mapped_column(Boolean,default=False)

class MCPReceipt(OAuthBase):
    __tablename__='assistant_mcp_receipts'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    request_digest: Mapped[str]=mapped_column(String(64))
    result: Mapped[dict|None]=mapped_column(JSON,nullable=True)
