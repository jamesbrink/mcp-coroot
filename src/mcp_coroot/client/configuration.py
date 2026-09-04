"""Project configuration.

Inspections, application categories, custom applications, cloud pricing and
integrations.
"""

from __future__ import annotations

from typing import Any

from .base import BaseAPI, Enveloped, JsonValue, split_envelope
from .errors import CorootValidationError
from .ids import encode_segment

#: Aliases used inside classes that define a ``list`` method.
JsonDicts = list[dict[str, Any]]
StrList = list[str]

#: Integration types accepted by ``/integrations/{type}``.
INTEGRATION_TYPES: tuple[str, ...] = (
    "prometheus",
    "clickhouse",
    "aws",
    "slack",
    "teams",
    "pagerduty",
    "opsgenie",
    "webhook",
)

NOTIFICATION_INTEGRATION_TYPES: tuple[str, ...] = (
    "slack",
    "teams",
    "pagerduty",
    "opsgenie",
    "webhook",
)


class InspectionsAPI(BaseAPI):
    async def list(self, project_id: str) -> Enveloped:
        """Every check with global/project thresholds and app overrides."""
        payload = await self._t.get(self.project_path(project_id, "inspections"))
        return split_envelope(payload)


class CategoriesAPI(BaseAPI):
    async def list(self, project_id: str) -> JsonDicts:
        data = await self._t.get(
            self.project_path(project_id, "application_categories")
        )
        return (
            [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []
        )

    async def get_form(self, project_id: str, name: str) -> dict[str, Any]:
        """The editable form for ``name`` (``""`` -> blank form with defaults)."""
        data = await self._t.get(
            self.project_path(project_id, "application_categories"),
            params={"name": name},
        )
        return data if isinstance(data, dict) else {}

    async def save(self, project_id: str, form: dict[str, Any]) -> None:
        """Create (``id`` empty) or update/rename (``id`` = existing name)."""
        await self._t.post(
            self.project_path(project_id, "application_categories"), form
        )

    async def delete(self, project_id: str, name: str) -> None:
        await self._t.post(
            self.project_path(project_id, "application_categories"),
            {"action": "delete", "id": name, "name": name},
        )

    async def test_notification(
        self, project_id: str, name: str, test: dict[str, Any]
    ) -> None:
        """Send a sample notification.

        ``test`` looks like ``{"incident": {"slack": {"channel": "ops"}}}``.
        """
        await self._t.post(
            self.project_path(project_id, "application_categories"),
            {"action": "test", "id": name, "name": name, "test": test},
        )


class CustomApplicationsAPI(BaseAPI):
    async def list(self, project_id: str) -> JsonDicts:
        data = await self._t.get(self.project_path(project_id, "custom_applications"))
        apps = data.get("custom_applications") if isinstance(data, dict) else None
        return [a for a in apps or [] if isinstance(a, dict)]

    async def save(
        self,
        project_id: str,
        *,
        name: str,
        instance_patterns: StrList,
        current_name: str | None = None,
    ) -> None:
        """Create, update or rename (``current_name`` != ``name``) a custom app."""
        if not instance_patterns:
            raise CorootValidationError(
                "Invalid request",
                detail="instance_patterns must not be empty (use delete instead)",
            )
        await self._t.post(
            self.project_path(project_id, "custom_applications"),
            {
                "name": current_name or name,
                "new_name": name,
                "instance_patterns": " ".join(instance_patterns),
            },
        )

    async def delete(self, project_id: str, name: str) -> None:
        await self._t.post(
            self.project_path(project_id, "custom_applications"),
            {"name": name, "new_name": name, "instance_patterns": ""},
        )


class CloudPricingAPI(BaseAPI):
    async def get(self, project_id: str) -> dict[str, Any]:
        data = await self._t.get(self.project_path(project_id, "custom_cloud_pricing"))
        return data if isinstance(data, dict) else {}

    async def set(
        self, project_id: str, *, per_cpu_core: float, per_memory_gb: float
    ) -> None:
        await self._t.post(
            self.project_path(project_id, "custom_cloud_pricing"),
            {
                "default": False,
                "per_cpu_core": per_cpu_core,
                "per_memory_gb": per_memory_gb,
            },
        )

    async def reset(self, project_id: str) -> None:
        await self._t.delete(self.project_path(project_id, "custom_cloud_pricing"))


class IntegrationsAPI(BaseAPI):
    async def list(self, project_id: str) -> dict[str, Any]:
        """Notification integrations plus the public ``base_url``."""
        data = await self._t.get(self.project_path(project_id, "integrations"))
        return data if isinstance(data, dict) else {}

    async def set_base_url(self, project_id: str, base_url: str) -> None:
        await self._t.put(
            self.project_path(project_id, "integrations"), {"base_url": base_url}
        )

    async def get(self, project_id: str, integration_type: str) -> JsonValue:
        return await self._t.get(
            self.project_path(
                project_id, "integrations", encode_segment(integration_type)
            )
        )

    async def save(
        self, project_id: str, integration_type: str, form: dict[str, Any]
    ) -> None:
        """Validate, test (where applicable) and store the integration."""
        await self._t.put(
            self.project_path(
                project_id, "integrations", encode_segment(integration_type)
            ),
            form,
        )

    async def test(
        self, project_id: str, integration_type: str, form: dict[str, Any]
    ) -> None:
        """Test without saving (sends a sample notification for chat/paging types)."""
        await self._t.post(
            self.project_path(
                project_id, "integrations", encode_segment(integration_type)
            ),
            form,
        )

    async def delete(self, project_id: str, integration_type: str) -> None:
        await self._t.delete(
            self.project_path(
                project_id, "integrations", encode_segment(integration_type)
            )
        )
