"""Accounts: who may sign in, their workspace, and their API keys.

Admission (D2): an identity is admitted when its subject is on the subject
allowlist or its verified email is on the email allowlist. Accounts are keyed
by (issuer, subject), never by email, so a second login with the same email
gets its own account. The first sign-in creates the user's one workspace.

API keys (D4) belong to a user and act in that user's workspace. The secret is
shown once; only its SHA-256 digest is stored, and every request re-checks it,
so revoking takes effect at once. A key's kind fixes where it works: ``rest``
keys on /api, ``mcp`` keys only on a future /mcp endpoint.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from slate.domain import Account, ApiKey, ApiKeyKind, Workspace

if TYPE_CHECKING:
    from uuid import UUID

    from slate.auth import Identity
    from slate.clock import Clock
    from slate.repositories.base import UnitOfWork, UnitOfWorkFactory

KEY_PREFIX = "slate_"
# last_used_at is a hint, not an audit log; refresh it at most this often.
TOUCH_EVERY = timedelta(minutes=5)


def is_admitted(identity: Identity, subjects: frozenset[str], emails: frozenset[str]) -> bool:
    """Subject on the allowlist, or a verified email on the allowlist."""
    if identity.subject in subjects:
        return True
    # The provider leaves email unset unless it is verified.
    return bool(identity.email) and identity.email.lower() in emails  # type: ignore[union-attr]


@dataclass(frozen=True)
class SignedIn:
    account: Account
    workspace: Workspace
    created: bool


async def sign_in(uow: UnitOfWork, identity: Identity) -> SignedIn:
    """Record the sign-in and return the account with its workspace, creating both if new."""
    account = await uow.users.record_sign_in(
        Account(
            issuer=identity.issuer,
            subject=identity.subject,
            name=identity.name,
            email=identity.email,
        )
    )
    workspace = await uow.workspaces.for_owner(account.id)
    created = workspace is None
    if workspace is None:
        workspace = await uow.workspaces.add(Workspace(owner_id=account.id))
    return SignedIn(account, workspace, created)


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


@dataclass(frozen=True)
class IssuedKey:
    key: ApiKey
    secret: str  # shown once


async def issue_key(
    uow: UnitOfWork, user_id: UUID, workspace_id: UUID, name: str, kind: ApiKeyKind
) -> IssuedKey:
    secret = KEY_PREFIX + secrets.token_urlsafe(32)
    key = await uow.api_keys.add(
        ApiKey(
            user_id=user_id,
            workspace_id=workspace_id,
            name=name,
            digest=digest(secret),
            kind=kind,
        )
    )
    return IssuedKey(key, secret)


async def revoke_key(uow: UnitOfWork, user_id: UUID, key_id: UUID, clock: Clock) -> bool:
    """Revoke one of ``user_id``'s keys. False when it is not theirs (or unknown)."""
    for key in await uow.api_keys.list_for_user(user_id):
        if key.id == key_id:
            if key.revoked_at is None:
                key.revoked_at = clock.now()
                await uow.api_keys.update(key)
            return True
    return False


@dataclass(frozen=True)
class KeyHolder:
    account: Account
    key: ApiKey


async def check_key(uow_factory: UnitOfWorkFactory, secret: str, clock: Clock) -> KeyHolder | None:
    """The live key and its owner for a presented secret, or None."""
    if not secret.startswith(KEY_PREFIX):
        return None
    async with uow_factory() as uow:
        key = await uow.api_keys.get_by_digest(digest(secret))
        if key is None or key.revoked_at is not None:
            return None
        account = await uow.users.get(key.user_id)
        if account is None:
            return None
        now = clock.now()
        if key.last_used_at is None or now - key.last_used_at >= TOUCH_EVERY:
            key.last_used_at = now
            await uow.api_keys.update(key)
            await uow.commit()
        return KeyHolder(account, key)
