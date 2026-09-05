"""Keep third-party credentials out of the model's context.

Coroot masks secrets in its API responses only for accounts that lack permission
to edit them (``form.Get(project, !isAllowed)`` in ``api/api.go``). This server
is normally configured with an Admin or Editor account, so integration and
database settings come back in clear: Slack bot tokens, PagerDuty and Opsgenie
keys, Teams webhook URLs, AWS access keys, and database passwords.

None of those are Coroot's to lose, and a tool result is copied into the client's
transcript. They are redacted here unless an operator opts in.
"""

from __future__ import annotations

import re
from typing import Any

#: Coroot's own placeholder for a secret it declines to reveal.
COROOT_PLACEHOLDER = "<hidden>"

#: What this server substitutes for a secret Coroot did reveal.
REDACTED = "<redacted by mcp-coroot>"

#: Values that must never be written back to Coroot as if they were real.
PLACEHOLDERS = frozenset({COROOT_PLACEHOLDER, REDACTED})

#: Field names that hold a credential. Matched case-insensitively against the
#: key, so `secret_access_key`, `basic_auth.password` and `webhook_url` all hit.
SECRET_KEY = re.compile(
    r"token|password|secret|api_key|access_key|integration_key|webhook_url",
    re.IGNORECASE,
)


def redact_secrets(value: Any, *, reveal: bool = False) -> Any:
    """Replace credential-bearing fields with :data:`REDACTED`.

    ``reveal`` passes the payload through untouched, for the operator who has
    set ``COROOT_REVEAL_SECRETS`` because they genuinely need to read a value
    back.
    """
    if reveal:
        return value
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if SECRET_KEY.search(str(key)) and value[key] not in (None, "", False)
                else redact_secrets(item, reveal=reveal)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item, reveal=reveal) for item in value]
    return value


def find_placeholders(value: Any, path: str = "") -> list[str]:
    """Find fields still holding a placeholder rather than a real secret."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            found.extend(find_placeholders(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(find_placeholders(item, f"{path}[{index}]"))
    elif isinstance(value, str) and value in PLACEHOLDERS:
        found.append(path or "(root)")
    return found
