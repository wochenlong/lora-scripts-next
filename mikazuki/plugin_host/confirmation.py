from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping


ConfirmationStatus = Literal["pending", "presented", "approved", "rejected", "expired"]


def request_hash(plugin_id: str, session_id: str, action: str, params: Mapping[str, Any] | None) -> str:
    """Stable identity of a Tool request (without its confirmationTicketId).

    A ticket authorizes exactly the request it was created for: the same
    plugin, the same session, the same action and the same parameters.  The
    volatile pi Tool-call id is deliberately NOT part of the identity, because
    an agent re-issues the call with a fresh id after the user approves —
    binding to the call id would make the two-step flow impossible.
    """
    clean = {key: value for key, value in dict(params or {}).items() if key != "confirmationTicketId"}
    canonical = json.dumps(
        {"pluginId": plugin_id, "sessionId": session_id, "action": action, "params": clean},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ConfirmationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code


@dataclass
class ConfirmationTicket:
    ticket_id: str
    plugin_id: str
    tool_call_id: str
    permission: str
    action: str
    title: str
    summary: str
    details: dict[str, Any]
    artifact_ids: list[str]
    created_at: datetime
    expires_at: datetime
    status: ConfirmationStatus = "pending"
    resolved_at: datetime | None = None
    resolution_note: str = ""
    params_hash: str | None = None
    consumed: bool = False
    claimed: bool = False

    def projection(self) -> dict[str, Any]:
        return {
            "ticketId": self.ticket_id,
            "pluginId": self.plugin_id,
            "toolCallId": self.tool_call_id,
            "permission": self.permission,
            "title": self.title,
            "summary": self.summary,
            "details": copy.deepcopy(self.details),
            "state": self.status,
            "action": self.action,
            "createdAt": self.created_at.isoformat(),
            "expiresAt": self.expires_at.isoformat(),
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
            "artifactIds": list(self.artifact_ids),
            "paramsHash": self.params_hash,
            "consumed": self.consumed,
        }

    def result(self) -> dict[str, Any]:
        return {
            "ticketId": self.ticket_id,
            "toolCallId": self.tool_call_id,
            "state": self.status,
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class ConfirmationTicketStore:
    """In-memory, one-shot Host confirmation tickets bound to a plugin Tool call."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._tickets: dict[str, ConfirmationTicket] = {}
        self._by_call: dict[tuple[str, str], str] = {}

    def create_pending(
        self,
        *,
        plugin_id: str,
        tool_call_id: str,
        permission: str,
        action: str,
        title: str,
        summary: str,
        details: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
        ttl_seconds: int = 300,
        params_hash: str | None = None,
    ) -> ConfirmationTicket:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (plugin_id, tool_call_id, permission, action, title)
        ):
            raise ValueError("confirmation identity, permission, action and title are required")
        artifacts = list(artifact_ids or ())
        if len(artifacts) != len(set(artifacts)) or any(not isinstance(value, str) or not value for value in artifacts):
            raise ValueError("confirmation artifact ids must be unique non-empty strings")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 3600:
            raise ValueError("confirmation ttl must be between 1 and 3600 seconds")
        now = self._now()
        key = (plugin_id, tool_call_id)
        with self._lock:
            existing_id = self._by_call.get(key)
            if existing_id is not None:
                existing = self._tickets[existing_id]
                self._expire(existing, now)
                if existing.status in {"pending", "presented"}:
                    raise ConfirmationError(
                        "CONFIRMATION_ALREADY_PENDING",
                        "A confirmation is already pending for this Tool call.",
                        status_code=409,
                    )
            ticket = ConfirmationTicket(
                ticket_id=secrets.token_urlsafe(32),
                plugin_id=plugin_id,
                tool_call_id=tool_call_id,
                permission=permission,
                action=action.strip(),
                title=title.strip(),
                summary=summary.strip(),
                details=copy.deepcopy(details or {}),
                artifact_ids=artifacts,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                params_hash=params_hash,
            )
            self._tickets[ticket.ticket_id] = ticket
            self._by_call[key] = ticket.ticket_id
            return ticket

    def request_projection(
        self,
        *,
        plugin_id: str,
        tool_call_id: str,
        granted_permissions: frozenset[str],
    ) -> dict[str, Any]:
        with self._lock:
            ticket = self._by_tool_call(plugin_id, tool_call_id)
            self._expire(ticket, self._now())
            self._require_permission(ticket, granted_permissions)
            if ticket.status == "expired":
                raise ConfirmationError("CONFIRMATION_EXPIRED", "The confirmation ticket has expired.", status_code=410)
            if ticket.status == "pending":
                ticket.status = "presented"
            return ticket.projection()

    def result(
        self,
        *,
        plugin_id: str,
        ticket_id: str,
        granted_permissions: frozenset[str],
    ) -> dict[str, Any]:
        with self._lock:
            ticket = self._ticket(plugin_id, ticket_id)
            self._expire(ticket, self._now())
            self._require_permission(ticket, granted_permissions)
            return ticket.result()

    def list_pending(self) -> list[dict[str, Any]]:
        now = self._now()
        with self._lock:
            projections = []
            for ticket in self._tickets.values():
                self._expire(ticket, now)
                if ticket.status in {"pending", "presented"}:
                    projections.append(ticket.projection())
            return sorted(projections, key=lambda item: item["createdAt"])

    def projection(self, ticket_id: str) -> dict[str, Any]:
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                raise ConfirmationError("CONFIRMATION_NOT_FOUND", "The confirmation ticket was not found.", status_code=404)
            self._expire(ticket, self._now())
            return ticket.projection()

    def consume(self, ticket_id: str) -> None:
        """Mark a successfully executed approval as used (one-shot).

        Unknown or unapproved tickets are ignored: consumption is a best-effort
        bookkeeping step after a successful Tool execution, never a gate.
        """
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is not None and ticket.status == "approved":
                ticket.consumed = True

    def claim(
        self,
        ticket_id: str,
        *,
        plugin_id: str | None = None,
        action: str | None = None,
        params_hash: str | None = None,
    ) -> dict[str, Any]:
        """Atomically gate-approve an approved ticket BEFORE executing its side effect.

        Unlike ``projection()`` + a later ``consume()``, this validates existence,
        expiry, binding (when supplied), the approved state and the one-shot
        status, and flips ``claimed``, all inside one lock section. Two concurrent
        executors of the same ticket can therefore never both pass the gate: the
        loser observes ``claimed`` and is rejected. The executor must call
        ``consume()`` on success and ``release()`` on failure (keeping the
        documented "a failed attempt may be retried" semantics).
        """
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                raise ConfirmationError("CONFIRMATION_NOT_FOUND", "The confirmation ticket was not found.", status_code=404)
            self._expire(ticket, self._now())
            if ticket.status == "expired":
                raise ConfirmationError("CONFIRMATION_EXPIRED", "The confirmation ticket has expired.", status_code=410)
            if (
                ticket.status != "approved"
                or ticket.consumed
                or ticket.claimed
                or (plugin_id is not None and ticket.plugin_id != plugin_id)
                or (action is not None and ticket.action != action)
                or (params_hash is not None and ticket.params_hash != params_hash)
            ):
                raise ConfirmationError(
                    "CONFIRMATION_MISMATCH",
                    "The confirmation ticket is not bound to this Tool request.",
                    status_code=409,
                )
            ticket.claimed = True
            return ticket.projection()

    def release(self, ticket_id: str) -> None:
        """Undo a claim after a failed execution so the approved request stays retryable."""
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is not None and not ticket.consumed:
                ticket.claimed = False

    def resolve(self, ticket_id: str, decision: Literal["approved", "rejected"], note: str = "") -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ConfirmationError("CONFIRMATION_DECISION_INVALID", "The confirmation decision is invalid.")
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                raise ConfirmationError("CONFIRMATION_NOT_FOUND", "The confirmation ticket was not found.", status_code=404)
            now = self._now()
            self._expire(ticket, now)
            if ticket.status == "expired":
                raise ConfirmationError("CONFIRMATION_EXPIRED", "The confirmation ticket has expired.", status_code=410)
            if ticket.status not in {"pending", "presented"}:
                raise ConfirmationError(
                    "CONFIRMATION_REPLAY_REJECTED",
                    "The confirmation ticket has already been resolved.",
                    status_code=409,
                )
            ticket.status = decision
            ticket.resolved_at = now
            ticket.resolution_note = note.strip()
            return ticket.projection()

    def _by_tool_call(self, plugin_id: str, tool_call_id: str) -> ConfirmationTicket:
        ticket_id = self._by_call.get((plugin_id, tool_call_id))
        if ticket_id is None:
            raise ConfirmationError("CONFIRMATION_NOT_FOUND", "The confirmation ticket was not found.", status_code=404)
        return self._tickets[ticket_id]

    def _ticket(self, plugin_id: str, ticket_id: str) -> ConfirmationTicket:
        ticket = self._tickets.get(ticket_id)
        if ticket is None or ticket.plugin_id != plugin_id:
            raise ConfirmationError("CONFIRMATION_NOT_FOUND", "The confirmation ticket was not found.", status_code=404)
        return ticket

    @staticmethod
    def _require_permission(ticket: ConfirmationTicket, granted_permissions: frozenset[str]) -> None:
        if ticket.permission not in granted_permissions:
            raise ConfirmationError(
                "CONFIRMATION_FORBIDDEN",
                "The plugin is not authorized for this confirmation.",
                status_code=403,
            )

    @staticmethod
    def _expire(ticket: ConfirmationTicket, now: datetime) -> None:
        if ticket.status in {"pending", "presented"} and now >= ticket.expires_at:
            ticket.status = "expired"

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("confirmation clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


__all__ = ["ConfirmationError", "ConfirmationTicket", "ConfirmationTicketStore"]
