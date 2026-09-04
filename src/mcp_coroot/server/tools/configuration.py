"""Tools for inspections, categories, custom apps, pricing and integrations."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.applications import (
    CHECK_IDS,
    INSTRUMENTATION_DEFAULT_PORTS,
    INSTRUMENTATION_TYPES,
)
from ...client.configuration import INTEGRATION_TYPES
from ...client.ids import PROJECT_SCOPE_APP_ID, normalize_app_id
from ...config import Settings
from ..app import DESTRUCTIVE, READ_ONLY, WRITE
from ..errors import guard, one_of
from ..state import AppState, ToolContext
from ._common import AppIdParam, ProjectIdParam, context, ok, respond, target

CheckIdParam = Annotated[
    str,
    Field(
        description=(
            "Check id from list_inspections, e.g. 'CPUContainer', 'SLOLatency', "
            "'StorageSpace', 'LogErrors'."
        )
    ),
]

IntegrationTypeParam = Annotated[
    str,
    Field(
        description=(
            "Integration type: 'prometheus', 'clickhouse', 'aws', 'slack', "
            "'teams', 'pagerduty', 'opsgenie' or 'webhook'."
        )
    ),
]

ScopeAppParam = Annotated[
    str | None,
    Field(
        description=(
            "Application id to scope the setting to. Omit for the project-wide default."
        )
    ),
]


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="List inspection checks", annotations=READ_ONLY)
    @guard
    async def list_inspections(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List Coroot's health checks with their thresholds and any overrides.

        Shows the built-in threshold, the project-wide override and per
        application overrides for each check.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.inspections.list(pid)
        data = result.data if isinstance(result.data, dict) else {}
        checks = [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "category": c.get("category"),
                "unit": c.get("unit"),
                "global_threshold": c.get("global_threshold"),
                "project_threshold": c.get("project_threshold"),
                "application_overrides": c.get("application_overrides"),
            }
            for c in (data.get("checks") or [])
            if isinstance(c, dict)
        ]
        return respond(
            state, {"project_id": pid, "count": len(checks), "checks": checks}
        )

    @mcp.tool(title="Get an inspection's configuration", annotations=READ_ONLY)
    @guard
    async def get_inspection_config(
        ctx: ToolContext,
        check_id: CheckIdParam,
        project_id: ProjectIdParam = None,
        app_id: ScopeAppParam = None,
    ) -> dict[str, Any]:
        """Get the threshold or SLO definition for one check.

        For simple checks the configs are positional: index 0 is Coroot's default,
        1 the project override and 2 the application override, with null meaning
        "not set".
        """
        state, pid = await target(ctx, project_id)
        scope = app_id or PROJECT_SCOPE_APP_ID
        data = await state.coroot.applications.get_inspection_config(
            pid, scope, one_of(check_id, CHECK_IDS, name="check_id")
        )
        return respond(
            state,
            {
                "project_id": pid,
                "check_id": check_id,
                "scope": "project" if scope == PROJECT_SCOPE_APP_ID else scope,
                **data,
            },
        )

    @mcp.tool(title="List application categories", annotations=READ_ONLY)
    @guard
    async def list_application_categories(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List application categories with their patterns and notification routing."""
        state, pid = await target(ctx, project_id)
        categories = await state.coroot.categories.list(pid)
        return respond(
            state,
            {"project_id": pid, "count": len(categories), "categories": categories},
        )

    @mcp.tool(title="List custom applications", annotations=READ_ONLY)
    @guard
    async def list_custom_applications(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List custom application definitions that group instances by pattern."""
        state, pid = await target(ctx, project_id)
        apps = await state.coroot.custom_applications.list(pid)
        return respond(
            state, {"project_id": pid, "count": len(apps), "custom_applications": apps}
        )

    @mcp.tool(title="List integrations", annotations=READ_ONLY)
    @guard
    async def list_integrations(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List notification integrations and which events each one receives.

        Metrics and data-source integrations (Prometheus, ClickHouse, AWS) are not
        listed here; read them with get_integration.
        """
        state, pid = await target(ctx, project_id)
        data = await state.coroot.integrations.list(pid)
        return respond(state, {"project_id": pid, **data})

    @mcp.tool(title="Get an integration's configuration", annotations=READ_ONLY)
    @guard
    async def get_integration(
        ctx: ToolContext,
        integration_type: IntegrationTypeParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Get one integration's settings. Secrets read back as '<hidden>'."""
        state, pid = await target(ctx, project_id)
        kind = one_of(integration_type, INTEGRATION_TYPES, name="integration_type")
        data = await state.coroot.integrations.get(pid, kind)
        payload = data if isinstance(data, dict) else {"value": data}
        return respond(state, {"project_id": pid, "type": kind, **payload})

    @mcp.tool(title="Get database instrumentation", annotations=READ_ONLY)
    @guard
    async def get_db_instrumentation(
        ctx: ToolContext,
        app_id: AppIdParam,
        db_type: Annotated[
            str,
            Field(
                description=(
                    "Database type: 'postgres', 'mysql', 'redis', 'mongodb' or "
                    "'memcached'."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Get the credentials and port Coroot uses to collect database statistics."""
        state, pid = await target(ctx, project_id)
        kind = one_of(db_type, INSTRUMENTATION_TYPES, name="db_type")
        data = await state.coroot.applications.get_instrumentation(pid, app_id, kind)
        return respond(
            state,
            {
                "project_id": pid,
                "application_id": normalize_app_id(app_id, project_id=pid),
                **data,
            },
        )

    @mcp.tool(title="Get cloud pricing", annotations=READ_ONLY)
    @guard
    async def get_cloud_pricing(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """Get the per-core and per-GB hourly prices used for cost estimates."""
        state, pid = await target(ctx, project_id)
        data = await state.coroot.cloud_pricing.get(pid)
        return respond(state, {"project_id": pid, **data})

    @mcp.tool(title="Get instance-wide settings", annotations=READ_ONLY)
    @guard
    async def get_server_settings(ctx: ToolContext) -> dict[str, Any]:
        """Get the Coroot instance's SSO, AI and Coroot Cloud configuration.

        SSO and AI provider settings are Enterprise features and read back empty
        on Community Edition.
        """
        state = context(ctx)
        sso = await state.coroot.system.sso()
        ai = await state.coroot.system.ai()
        cloud = await state.coroot.system.cloud_status()
        return respond(
            state,
            {
                "sso": sso,
                "ai": ai,
                "cloud": cloud,
                "base_url": state.settings.base_url,
            },
        )

    if settings.read_only:
        return

    @mcp.tool(title="Set an inspection threshold", annotations=WRITE)
    @guard
    async def update_inspection_config(
        ctx: ToolContext,
        check_id: CheckIdParam,
        config: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "The form to save, in the shape get_inspection_config "
                    'returned. Simple checks take {"configs": [null, '
                    '{"threshold": 90}, null]} where index 1 is the project '
                    "override and index 2 the application override; null clears "
                    "an override."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
        app_id: ScopeAppParam = None,
    ) -> dict[str, Any]:
        """Change a check's threshold, or define a custom SLO.

        Read the current form with get_inspection_config first: the positional
        layout matters.
        """
        state, pid = await target(ctx, project_id)
        scope = app_id or PROJECT_SCOPE_APP_ID
        await state.coroot.applications.set_inspection_config(
            pid, scope, one_of(check_id, CHECK_IDS, name="check_id"), config
        )
        return ok(
            f"Updated {check_id} configuration", project_id=pid, check_id=check_id
        )

    @mcp.tool(title="Create or update an application category", annotations=WRITE)
    @guard
    async def save_application_category(
        ctx: ToolContext,
        name: Annotated[
            str,
            Field(
                description=(
                    "Category name: at least 3 characters of lowercase letters, "
                    "digits, '-' or '_'."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
        custom_patterns: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Glob patterns matching 'namespace/application-name', e.g. "
                    "['staging/*', 'default/api-*']. Omit to keep the existing "
                    "patterns."
                )
            ),
        ] = None,
        current_name: Annotated[
            str | None,
            Field(description="Existing category name when renaming or updating one."),
        ] = None,
        notification_settings: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Notification routing for incidents, deployments and alerts, "
                    "in the shape list_application_categories returns. Omit to "
                    "keep the existing routing."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create an application category, or update an existing one.

        Categories drive grouping and notification routing. Pass current_name to
        edit or rename one; anything you leave out keeps its current value,
        because Coroot replaces the whole category on save.
        """
        state, pid = await target(ctx, project_id)
        # Coroot's save is a full replace: an omitted field is stored as empty.
        # Start from the current form so partial updates do not wipe the rest.
        form = await state.coroot.categories.get_form(pid, current_name or "")
        form["action"] = ""
        form["id"] = current_name or ""
        form["name"] = name
        if custom_patterns is not None:
            form["custom_patterns"] = " ".join(custom_patterns)
        if notification_settings is not None:
            form["notification_settings"] = notification_settings
        await state.coroot.categories.save(pid, form)
        return ok(f"Saved category {name!r}", project_id=pid, name=name)

    @mcp.tool(title="Delete an application category", annotations=DESTRUCTIVE)
    @guard
    async def delete_application_category(
        ctx: ToolContext,
        name: Annotated[str, Field(description="Category name to delete.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Delete a custom application category. Built-in categories are kept."""
        state, pid = await target(ctx, project_id)
        await state.coroot.categories.delete(pid, name)
        return ok(f"Deleted category {name!r}", project_id=pid, name=name)

    @mcp.tool(title="Create or update a custom application", annotations=WRITE)
    @guard
    async def save_custom_application(
        ctx: ToolContext,
        name: Annotated[
            str, Field(description="Custom application name (slug format).")
        ],
        instance_patterns: Annotated[
            list[str],
            Field(
                description="Glob patterns matching instance names, e.g. ['worker-*'].",
                min_length=1,
            ),
        ],
        project_id: ProjectIdParam = None,
        current_name: Annotated[
            str | None, Field(description="Existing name when renaming or updating.")
        ] = None,
    ) -> dict[str, Any]:
        """Group instances that Coroot did not detect as one application."""
        state, pid = await target(ctx, project_id)
        await state.coroot.custom_applications.save(
            pid,
            name=name,
            instance_patterns=instance_patterns,
            current_name=current_name,
        )
        return ok(f"Saved custom application {name!r}", project_id=pid, name=name)

    @mcp.tool(title="Delete a custom application", annotations=DESTRUCTIVE)
    @guard
    async def delete_custom_application(
        ctx: ToolContext,
        name: Annotated[str, Field(description="Custom application name to delete.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Delete a custom application definition."""
        state, pid = await target(ctx, project_id)
        await state.coroot.custom_applications.delete(pid, name)
        return ok(f"Deleted custom application {name!r}", project_id=pid, name=name)

    @mcp.tool(title="Configure an integration", annotations=WRITE)
    @guard
    async def configure_integration(
        ctx: ToolContext,
        integration_type: IntegrationTypeParam,
        config: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "Integration settings. slack: {token, default_channel, "
                    "incidents, deployments, alerts}. pagerduty: "
                    "{integration_key, incidents, alerts}. opsgenie: {api_key, "
                    "eu_instance, incidents, alerts}. teams: {channels: "
                    "[{name, webhook_url}], default_channel, ...}. webhook: "
                    "{url, incident_template, ...}. prometheus: {url, "
                    "refresh_interval, basic_auth, extra_selector}. clickhouse: "
                    "{protocol, addr, auth, database}. aws: {region, "
                    "access_key_id, secret_access_key}."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
        test_only: Annotated[
            bool,
            Field(
                description=(
                    "Test the settings without saving. Chat and paging "
                    "integrations send a sample notification."
                )
            ),
        ] = False,
    ) -> dict[str, Any]:
        """Configure or test a notification or data-source integration.

        Coroot validates and connects before saving, so an invalid endpoint or
        token is reported as an error. Read the current shape with
        get_integration first.
        """
        state, pid = await target(ctx, project_id)
        kind = one_of(integration_type, INTEGRATION_TYPES, name="integration_type")
        if test_only:
            await state.coroot.integrations.test(pid, kind, config)
            return ok(f"{kind} integration test succeeded", project_id=pid, type=kind)
        await state.coroot.integrations.save(pid, kind, config)
        return ok(f"Configured {kind} integration", project_id=pid, type=kind)

    @mcp.tool(title="Delete an integration", annotations=DESTRUCTIVE)
    @guard
    async def delete_integration(
        ctx: ToolContext,
        integration_type: IntegrationTypeParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Remove an integration.

        Prometheus cannot be removed this way: a project always needs a metrics
        source. Replace it with configure_integration instead.
        """
        state, pid = await target(ctx, project_id)
        kind = one_of(integration_type, INTEGRATION_TYPES, name="integration_type")
        await state.coroot.integrations.delete(pid, kind)
        return ok(f"Deleted {kind} integration", project_id=pid, type=kind)

    @mcp.tool(title="Set the notification base URL", annotations=WRITE)
    @guard
    async def set_notification_base_url(
        ctx: ToolContext,
        base_url: Annotated[
            str,
            Field(
                description=(
                    "Public Coroot URL used in notification links, e.g. "
                    "'https://coroot.example.com'."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Set the public URL Coroot puts in notification links."""
        state, pid = await target(ctx, project_id)
        await state.coroot.integrations.set_base_url(pid, base_url)
        return ok("Updated notification base URL", project_id=pid, base_url=base_url)

    @mcp.tool(title="Configure database instrumentation", annotations=WRITE)
    @guard
    async def configure_db_instrumentation(
        ctx: ToolContext,
        app_id: AppIdParam,
        db_type: Annotated[
            str,
            Field(
                description=(
                    "Database type: 'postgres', 'mysql', 'redis', 'mongodb' or "
                    "'memcached'."
                )
            ),
        ],
        username: Annotated[
            str | None, Field(description="Username Coroot should connect with.")
        ] = None,
        password: Annotated[
            str | None, Field(description="Password for that user.")
        ] = None,
        port: Annotated[
            str | None,
            Field(
                description=(
                    "Port to connect to. Defaults to the standard port for the engine."
                )
            ),
        ] = None,
        enabled: Annotated[
            bool, Field(description="Whether to collect statistics.")
        ] = True,
        params: Annotated[
            dict[str, str] | None,
            Field(
                description="Extra connection parameters, e.g. {'sslmode': 'disable'}."
            ),
        ] = None,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Let Coroot log into a database to collect its internal statistics.

        This unlocks the engine-specific reports (query latency, replication lag,
        connection counts) that plain metrics cannot provide.
        """
        state, pid = await target(ctx, project_id)
        kind = one_of(db_type, INSTRUMENTATION_TYPES, name="db_type")
        config: dict[str, Any] = {
            "type": kind,
            "port": port or INSTRUMENTATION_DEFAULT_PORTS[kind],
            "credentials": {"username": username or "", "password": password or ""},
            "params": params or {},
            "enabled": enabled,
        }
        await state.coroot.applications.set_instrumentation(pid, app_id, config)
        return ok(
            f"Configured {kind} instrumentation",
            project_id=pid,
            application_id=normalize_app_id(app_id, project_id=pid),
        )

    @mcp.tool(title="Link a telemetry service to an application", annotations=WRITE)
    @guard
    async def link_telemetry_service(
        ctx: ToolContext,
        app_id: AppIdParam,
        kind: Annotated[
            str,
            Field(
                description="Which telemetry to link: 'profiling', 'tracing' or 'logs'."
            ),
        ],
        service: Annotated[
            str,
            Field(
                description=(
                    "OpenTelemetry service name reporting that data. Empty string "
                    "unlinks."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Tell Coroot which OpenTelemetry service belongs to an application.

        Use it when traces, logs or profiles arrive under a service name Coroot
        did not match automatically.
        """
        state, pid = await target(ctx, project_id)
        which = one_of(kind, ("profiling", "tracing", "logs"), name="kind")
        setter = {
            "profiling": state.coroot.applications.set_profiling_service,
            "tracing": state.coroot.applications.set_tracing_service,
            "logs": state.coroot.applications.set_logs_service,
        }[which]
        await setter(pid, app_id, service)
        return ok(
            f"Linked {which} service {service!r}",
            project_id=pid,
            application_id=normalize_app_id(app_id, project_id=pid),
        )

    @mcp.tool(title="Set cloud pricing", annotations=WRITE)
    @guard
    async def set_cloud_pricing(
        ctx: ToolContext,
        per_cpu_core: Annotated[
            float, Field(description="Hourly price of one CPU core.", gt=0)
        ],
        per_memory_gb: Annotated[
            float, Field(description="Hourly price of one GB of memory.", gt=0)
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Override the default cloud pricing used for cost estimates."""
        state, pid = await target(ctx, project_id)
        await state.coroot.cloud_pricing.set(
            pid, per_cpu_core=per_cpu_core, per_memory_gb=per_memory_gb
        )
        return ok("Updated cloud pricing", project_id=pid)

    @mcp.tool(title="Reset cloud pricing", annotations=DESTRUCTIVE)
    @guard
    async def reset_cloud_pricing(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """Drop custom pricing and go back to Coroot's built-in rates."""
        state, pid = await target(ctx, project_id)
        await state.coroot.cloud_pricing.reset(pid)
        return ok("Reset cloud pricing to defaults", project_id=pid)
