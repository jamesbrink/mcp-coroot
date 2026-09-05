"""The composed :class:`CorootClient`."""

from __future__ import annotations

from types import TracebackType
from typing import Self

import httpx2 as httpx

from ..config import Settings
from .accounts import AuthAPI, SystemAPI, UsersAPI
from .applications import ApplicationsAPI, NodesAPI
from .base import Transport
from .configuration import (
    CategoriesAPI,
    CloudPricingAPI,
    CustomApplicationsAPI,
    InspectionsAPI,
    IntegrationsAPI,
)
from .dashboards import DashboardsAPI
from .incidents import AlertingRulesAPI, AlertsAPI, IncidentsAPI
from .metrics import MetricsAPI
from .overview import OverviewAPI
from .projects import ProjectsAPI


class CorootClient:
    """Async client covering the whole Coroot management API.

    Usage::

        async with CorootClient(Settings.from_env()) as coroot:
            projects = await coroot.projects.list()
            apps = await coroot.overview.applications(projects[0]["id"])
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.transport = Transport(self.settings, transport=transport)
        t = self.transport
        self.auth = AuthAPI(t)
        self.users = UsersAPI(t)
        self.system = SystemAPI(t)
        self.projects = ProjectsAPI(t)
        self.overview = OverviewAPI(t)
        self.applications = ApplicationsAPI(t)
        self.nodes = NodesAPI(t)
        self.incidents = IncidentsAPI(t)
        self.alerts = AlertsAPI(t)
        self.alerting_rules = AlertingRulesAPI(t)
        self.dashboards = DashboardsAPI(t)
        self.inspections = InspectionsAPI(t)
        self.categories = CategoriesAPI(t)
        self.custom_applications = CustomApplicationsAPI(t)
        self.cloud_pricing = CloudPricingAPI(t)
        self.integrations = IntegrationsAPI(t)
        self.metrics = MetricsAPI(t)

    async def aclose(self) -> None:
        await self.transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
