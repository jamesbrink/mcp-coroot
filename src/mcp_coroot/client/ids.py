"""Identifier helpers mirroring Coroot's ``model.ApplicationId`` rules."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

#: The zero application id: project-wide scope for inspection configuration.
PROJECT_SCOPE_APP_ID = "::"

EXTERNAL_CLUSTER_ID = "external"
EXTERNAL_SERVICE_KIND = "ExternalService"


class InvalidApplicationId(ValueError):
    """The value is not a ``cluster:namespace:Kind:name`` application id."""


@dataclass(frozen=True, slots=True)
class ApplicationId:
    """A parsed Coroot application id.

    Coroot serialises ids as four colon separated parts:
    ``<cluster_id>:<namespace>:<Kind>:<name>`` (e.g.
    ``hwvop6p7:default:Deployment:checkout``). Non-Kubernetes workloads use ``_`` as
    the namespace, and the name itself may contain colons.
    """

    cluster_id: str
    namespace: str
    kind: str
    name: str

    @classmethod
    def parse(cls, value: str, *, fallback_cluster_id: str = "") -> ApplicationId:
        """Parse ``value`` exactly like ``model.NewApplicationIdFromString``."""
        text = value.strip()
        parts = text.split(":", 3)
        if len(parts) == 3:
            cluster, namespace, kind, name = "", parts[0], parts[1], parts[2]
        elif len(parts) == 4:
            cluster, namespace, kind, name = parts
            if cluster == EXTERNAL_CLUSTER_ID and namespace != EXTERNAL_CLUSTER_ID:
                # 3-part id whose name contains a colon.
                cluster, namespace, kind = "", parts[0], parts[1]
                name = f"{parts[2]}:{parts[3]}"
        else:
            raise InvalidApplicationId(
                f"invalid application id {value!r}: expected "
                "'cluster_id:namespace:Kind:name'"
            )
        if not cluster:
            cluster = fallback_cluster_id
        if kind == EXTERNAL_SERVICE_KIND:
            cluster = EXTERNAL_CLUSTER_ID
        return cls(cluster_id=cluster, namespace=namespace, kind=kind, name=name)

    def __str__(self) -> str:
        return f"{self.cluster_id}:{self.namespace}:{self.kind}:{self.name}"

    @property
    def short(self) -> str:
        """The ``namespace:Kind:name`` form used by selectors and glob patterns."""
        return f"{self.namespace}:{self.kind}:{self.name}"

    @property
    def is_project_scope(self) -> bool:
        return not (self.cluster_id or self.namespace or self.kind or self.name)

    @property
    def is_complete(self) -> bool:
        """True when the id carries a cluster id and can be looked up server side."""
        return bool(self.cluster_id and self.kind and self.name)


def normalize_app_id(value: str, *, project_id: str | None = None) -> str:
    """Return the 4-part id Coroot expects, filling in the cluster id if omitted.

    Coroot looks applications up by their full id, so a 3-part id would silently
    match nothing. When the cluster id is missing we default it to ``project_id``
    (the cluster id of applications discovered by that project).
    """
    if value.strip() == PROJECT_SCOPE_APP_ID:
        return PROJECT_SCOPE_APP_ID
    parsed = ApplicationId.parse(value, fallback_cluster_id=project_id or "")
    return str(parsed)


def encode_segment(value: str) -> str:
    """Percent-encode one path segment (``:`` and ``+`` included).

    Coroot registers routes with ``UseEncodedPath`` and query-unescapes the ``{app}``
    and ``{node}`` variables, so a literal ``+`` must be sent as ``%2B``.
    """
    return quote(value, safe="")
