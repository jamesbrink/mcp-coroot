"""Tests for opt-in bounded projections.

Contract: ``summary`` params on ``get_application`` /
``get_applications_overview``; ``summary=False`` is passthrough,
``summary=True`` returns a bounded projection instead of the payload.

Conservation rule per test: each docstring names its literal guarantee and the
production mutation that would redden it (no AC refs).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_coroot.client import CorootError
from mcp_coroot.projection import summarize_application, summarize_overview
from mcp_coroot.server import get_application_impl, get_applications_overview_impl

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def wire_bytes(payload: dict) -> int:
    return len(json.dumps(payload).encode())


class TestSummarizeOverview:
    def test_counts_add_up_and_caps_named(self):
        """Counts carry
        returned+truncated+malformed==total.

        Rougit si summarize_overview cesse de compter les entrees
        non-dict dans applications_malformed (symbole: malformed).
        """
        overview = load("overview_full.json")
        proj = summarize_overview(overview, max_apps=50)
        counts = proj["counts"]
        assert counts["applications_total"] == 210
        assert counts["applications_returned"] == 50
        assert counts["applications_truncated"] == 160
        assert counts["applications_malformed"] == 0
        assert (
            counts["applications_returned"]
            + counts["applications_truncated"]
            + counts["applications_malformed"]
            == counts["applications_total"]
        )
        assert proj["limits"] == {"max_apps": 50}
        assert proj["projected"] is True

    def test_identity_and_health_kept_chart_payload_dropped(self):
        """Identity/health kept,
        chart payload dropped.

        Rougit si _summarize_overview_app recopie la cle chart du
        signal (symbole: _signal_value, changement: return signal brut).
        """
        overview = load("overview_full.json")
        proj = summarize_overview(overview, max_apps=50)
        first = proj["applications"][0]
        assert first["id"].startswith("proj9x:")
        assert set(first["latency"]) == {"status", "value"}
        assert "chart" not in json.dumps(first)

    def test_directory_dropped_with_counts_never_replicated(self):
        """Directory dropped,
        counts carried, never replicated.

        Rougit si summarize_overview remet directory_ids dans
        l'enveloppe (symbole: directory_ids, changement: liste replicee).
        """
        overview = load("overview_full.json")
        proj = summarize_overview(overview, max_apps=50)
        assert "directory_ids" not in proj
        assert proj["counts"]["directory_total"] == 283
        assert proj["counts"]["directory_dropped"] == 283
        assert proj["counts"]["directory_returned"] == 0
        assert proj["dropped"]["directory_ids"] == 283

    def test_contract_dropped_key_present(self):
        """Envelope carries
        the promised dropped key.

        Rougit si la cle dropped est retiree de summarize_overview
        (symbole: dropped, changement: cle supprimee).
        """
        proj = summarize_overview(load("overview_full.json"))
        assert proj["dropped"]["directory_ids"] == 283
        assert (
            proj["dropped"]["chart_payloads"] == proj["counts"]["applications_returned"]
        )

    def test_unknown_vs_absent_signals(self):
        """Unknown kept as value,
        absent stays absent.

        Rougit si _signal_value ecrase un signal unknown sans value
        (symbole: _signal_value, changement: retour {"status":None}).
        """
        overview = load("overview_full.json")
        proj = summarize_overview(overview, max_apps=210)
        unknowns = [
            a
            for a in proj["applications"]
            if isinstance(a.get("errors"), dict)
            and a["errors"].get("status") == "unknown"
        ]
        assert unknowns, "fixture must contain an unknown-status signal"
        assert unknowns[0]["errors"]["value"] == ""
        no_dns = [a for a in overview["data"]["applications"] if "dns" not in a]
        if no_dns:
            missing_id = no_dns[0]["id"]
            match = [a for a in proj["applications"] if a["id"] == missing_id]
            assert match and "dns" not in match[0]

    def test_malformed_apps_counted_not_conflated(self):
        """Non-dict apps counted
        as malformed, not truncated.

        Rougit si summarize_overview confond entree malformee et
        troncature de cap (symbole: applications_malformed).
        """
        overview = load("overview_full.json")
        overview["data"]["applications"].insert(0, "GARBAGE")
        overview["data"]["applications"].append(None)
        proj = summarize_overview(overview, max_apps=500)
        counts = proj["counts"]
        assert counts["applications_malformed"] == 2
        assert counts["applications_total"] == 212
        assert (
            counts["applications_returned"]
            + counts["applications_truncated"]
            + counts["applications_malformed"]
            == counts["applications_total"]
        )

    def test_invalid_cap_is_validation_error(self):
        """Invalid cap raises
        before any HTTP.

        Rougit si le seuil max_apps<1 cesse de lever (symbole:
        _check_caps, changement: seuil retire).
        """
        with pytest.raises(ValueError):
            summarize_overview(load("overview_full.json"), max_apps=0)


class TestSummarizeApplication:
    def test_no_silent_dependency_loss(self):
        """Every client/dependency
        id preserved + unbounded named.

        Rougit si dependency_ids est derive des seuls noeuds gardes
        (symbole: dependency_ids, changement: boucle sur sliced).
        """
        application = load("application_full.json")
        proj = summarize_application(application, max_nodes=2)
        full_deps = {
            d["id"] for d in application["data"]["app_map"]["dependencies"]
        } | {c["id"] for c in application["data"]["app_map"]["clients"]}
        assert set(proj["dependency_ids"]) == full_deps
        assert proj["counts"]["dependencies_total"] == 9
        assert proj["counts"]["clients_total"] == 2
        assert proj["unbounded"] == ["dependency_ids"]

    def test_charts_collapsed_tables_truncated_with_counts(self):
        """Chart/chart_group/heatmap
        collapsed, tables capped.

        Rougit si _summarize_widget recopie series/data brutes
        (symbole: points_dropped, changement: pas de comptage).
        """
        application = load("application_full.json")
        proj = summarize_application(application, max_table_rows=2)
        by_name = {r["name"]: r for r in proj["reports"]}
        kinds = {
            name: sorted({w["kind"] for w in rep["widgets"]})
            for name, rep in by_name.items()
        }
        assert kinds["SLO"] == ["chart", "table"]
        assert kinds["CPU"] == ["chart"]
        assert kinds["Logs"] == ["logs"]
        assert "Deployments" in by_name
        table = by_name["Deployments"]["widgets"][0]
        assert table["kind"] == "table"
        assert table["rows_total"] == 81
        assert table["rows_returned"] == 2
        assert table["rows_truncated"] == 79
        assert (
            table["rows_returned"] + table["rows_truncated"] + table["rows_malformed"]
            == table["rows_total"]
        )
        assert by_name["CPU"]["widgets"][0]["points_dropped"] > 0
        assert by_name["CPU"]["widgets"][0]["source"] == "chart_group"
        heatmaps = [
            w
            for r in proj["reports"]
            for w in r["widgets"]
            if w.get("source") == "heatmap"
        ]
        assert heatmaps and heatmaps[0]["points_dropped"] > 0

    def test_logs_profiling_tracing_other_branches(self):
        """Logs/profiling/tracing/other
        widget branches.

        Rougit si une branche widget rend kind other par defaut
        (symbole: _summarize_widget, changement: branche supprimee).
        """
        proj = summarize_application(load("application_full.json"))
        by_name = {r["name"]: r for r in proj["reports"]}
        logs = by_name["Logs"]["widgets"][0]
        assert logs["kind"] == "logs"
        assert logs["application_id"].startswith("proj9x:")
        assert logs["check"]["id"] == "LogErrors"
        kinds_all = [w["kind"] for r in proj["reports"] for w in r["widgets"]]
        assert "profiling" in kinds_all
        assert "tracing" in kinds_all
        other = summarize_application(
            {
                "context": {},
                "data": {
                    "app_map": {},
                    "reports": [
                        {
                            "name": "X",
                            "status": "ok",
                            "checks": [],
                            "widgets": [{"future_kind": {"a": 1}}],
                        }
                    ],
                },
            }
        )["reports"][0]["widgets"][0]
        assert other["kind"] == "other"
        assert other["keys"] == ["future_kind"]
        malformed = summarize_application(
            {
                "context": {},
                "data": {
                    "app_map": {},
                    "reports": [
                        {
                            "name": "X",
                            "status": "ok",
                            "checks": [],
                            "widgets": [
                                "GARBAGE",
                                {"table": {"header": [], "rows": []}},
                            ],
                        }
                    ],
                },
            }
        )["reports"][0]["widgets"]
        assert [w["kind"] for w in malformed] == ["table"]

    def test_categories_fallback_to_app_map(self):
        """Categories fall back to app_map.categories.

        Rougit si summarize_application lit data.categories seul
        (symbole: categories, changement: pas de repli app_map).
        """
        proj = summarize_application(load("application_full.json"))
        assert proj["categories"] == ["control-plane", "monitoring"]

    def test_instances_summarized_not_raw(self):
        """Instance nodes summarized and counted in cap.

        Rougit si les instances repassent brutes hors cap
        (symbole: _summarize_node, changement: carve-out instances).
        """
        application = load("application_full.json")
        proj = summarize_application(application)
        instance_nodes = [
            (n, k)
            for n, k in zip(proj["nodes"], proj["node_kinds"], strict=True)
            if k == "instances"
        ]
        assert instance_nodes
        for node, _ in instance_nodes:
            assert "indicators_truncated" in node or "link_stats_count" in node

    def test_node_truncation_is_explicit(self):
        """Node truncation explicit with conservation.

        Rougit si nodes_truncated ignore les noeuds malformes
        (symbole: nodes_malformed, changement: compteur retire).
        """
        proj = summarize_application(load("application_full.json"), max_nodes=2)
        counts = proj["counts"]
        assert counts["nodes_total"] == 13
        assert counts["nodes_returned"] == 2
        assert counts["nodes_truncated"] == 11
        assert (
            counts["nodes_returned"]
            + counts["nodes_truncated"]
            + counts["nodes_malformed"]
            == counts["nodes_total"]
        )
        full = summarize_application(load("application_full.json"))
        assert full["counts"]["nodes_truncated"] == 0

    def test_malformed_rows_and_nodes_counted_separately(self):
        """Malformed rows/nodes distinct from truncation.

        Rougit si une ligne non-dict est comptee en troncature
        (symbole: rows_malformed, changement: compteur retire).
        """
        application = load("application_full.json")
        for report in application["data"]["reports"]:
            if report["name"] == "Deployments":
                report["widgets"][0]["table"]["rows"].insert(0, "GARBAGE-ROW")
                break
        application["data"]["app_map"]["dependencies"].append("GARBAGE-NODE")
        proj = summarize_application(application, max_table_rows=5)
        table = next(r for r in proj["reports"] if r["name"] == "Deployments")[
            "widgets"
        ][0]
        assert table["rows_malformed"] == 1
        assert table["rows_total"] == 82
        assert (
            table["rows_returned"] + table["rows_truncated"] + table["rows_malformed"]
            == table["rows_total"]
        )
        assert proj["counts"]["nodes_malformed"] == 1
        assert proj["counts"]["nodes_total"] == 14

    def test_invalid_caps_are_validation_errors(self):
        """Invalid caps raise before any HTTP.

        Rougit si un seuil cesse de lever (symbole: _check_caps,
        changement: minimum retire).
        """
        application = load("application_full.json")
        with pytest.raises(ValueError):
            summarize_application(application, max_table_rows=-1)
        with pytest.raises(ValueError):
            summarize_application(application, max_nodes=0)


class TestProjectionEntrypoints:
    async def test_overview_default_byte_identical_single_request(self):
        """Overview default byte-identical, one request.

        Rougit si summary=False cesse de renvoyer le payload tel quel
        (symbole: get_applications_overview_impl, changement: cle ajoutee).
        """
        overview = load("overview_full.json")
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_applications_overview.return_value = overview
            mock_get_client.return_value = mock_client
            result = await get_applications_overview_impl("proj9x")
            assert result == {"success": True, "overview": overview}
            assert mock_client.get_applications_overview.call_count == 1

    async def test_application_default_byte_identical_single_request(self):
        """Application default byte-identical, one request.

        Rougit si summary=False cesse de renvoyer le payload tel quel
        (symbole: get_application_impl, changement: cle ajoutee).
        """
        application = load("application_full.json")
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.return_value = application
            mock_get_client.return_value = mock_client
            result = await get_application_impl(
                "proj9x", "proj9x:lambda:Deployment:lambda-svc-01"
            )
            assert result == {"success": True, "application": application}
            assert mock_client.get_application.call_count == 1

    async def test_overview_summary_omits_raw_wire_shrinks(self):
        """Summary omits raw, wire bytes shrink.

        Rougit si summary=True re-embarque le payload brut
        (symbole: get_applications_overview_impl, changement: cle overview).
        """
        overview = load("overview_full.json")
        full_bytes = wire_bytes({"success": True, "overview": overview})
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_applications_overview.return_value = overview
            mock_get_client.return_value = mock_client
            result = await get_applications_overview_impl(
                "proj9x", summary=True, max_apps=50
            )
            assert mock_client.get_applications_overview.call_count == 1
            assert "overview" not in result
            assert result["success"] is True
            assert result["projection"]["counts"]["applications_total"] == 210
            assert wire_bytes(result) < full_bytes
            first_id = result["projection"]["applications"][0]["id"]
            assert first_id.startswith("proj9x:")

    async def test_application_summary_omits_raw_wire_shrinks(self):
        """Summary omits raw, wire bytes shrink.

        Rougit si summary=True re-embarque le payload brut
        (symbole: get_application_impl, changement: cle application).
        """
        application = load("application_full.json")
        full_bytes = wire_bytes({"success": True, "application": application})
        assert full_bytes > 0
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.return_value = application
            mock_get_client.return_value = mock_client
            result = await get_application_impl(
                "proj9x", "proj9x:lambda:Deployment:lambda-svc-01", summary=True
            )
            assert mock_client.get_application.call_count == 1
            assert "application" not in result
            assert wire_bytes(result) < full_bytes
            proj = result["projection"]
            assert "proj9x:alpha:Deployment:alpha-svc-02" in proj["dependency_ids"]
            assert "summary=False" in proj["detail"]["how"]

    async def test_invalid_caps_zero_http_calls(self):
        """Invalid caps: validation envelope, zero HTTP calls.

        Rougit si la validation repasse APRES le fetch
        (symbole: check_overview_caps, changement: appel deplace).
        """
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            result = await get_applications_overview_impl(
                "proj9x", summary=True, max_apps=0
            )
            assert result["success"] is False
            assert result["error_type"] == "validation"
            assert mock_client.get_applications_overview.call_count == 0
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            result = await get_application_impl(
                "proj9x", "proj9x:x", summary=True, max_table_rows=-1
            )
            assert result["success"] is False
            assert result["error_type"] == "validation"
            assert mock_client.get_application.call_count == 0

    async def test_projection_error_semantics_preserved(self):
        """Error/auth passthrough preserved with summary=True.

        Rougit si handle_errors cesse de mapper CorootError
        (symbole: handle_errors, changement: mapping retire).
        """
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_applications_overview.side_effect = CorootError(
                "Authentication failed: bad cookie"
            )
            mock_get_client.return_value = mock_client
            result = await get_applications_overview_impl("proj9x", summary=True)
            assert result["success"] is False
            assert result["error_type"] == "authentication"
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.side_effect = CorootError(
                "API request failed: 400 - invalid application id"
            )
            mock_get_client.return_value = mock_client
            result = await get_application_impl("proj9x", "proj9x:bad", summary=True)
            assert result["success"] is False
            assert result["error_type"] == "api_error"
