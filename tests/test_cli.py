"""Tests for the command line entry point."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mcp_coroot.cli import build_parser, main


def test_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"
    assert args.read_only is False


def test_http_options() -> None:
    args = build_parser().parse_args(
        ["--transport", "http", "--port", "9000", "--stateless", "--json-response"]
    )
    assert (args.transport, args.port) == ("http", 9000)
    assert args.stateless and args.json_response


def test_check_prints_redacted_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COROOT_BASE_URL", "https://coroot.example.com")
    monkeypatch.setenv("COROOT_USERNAME", "admin")
    monkeypatch.setenv("COROOT_PASSWORD", "hunter2")
    assert main(["--check"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["base_url"] == "https://coroot.example.com"
    assert printed["auth_mode"] == "password"
    assert "hunter2" not in json.dumps(printed)


def test_check_honours_read_only_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COROOT_BASE_URL", "http://localhost:8080")
    monkeypatch.delenv("COROOT_READ_ONLY", raising=False)
    assert main(["--check", "--read-only"]) == 0
    assert json.loads(capsys.readouterr().out)["read_only"] is True


def test_invalid_configuration_exits_with_code_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COROOT_BASE_URL", "not-a-url")
    assert main(["--check"]) == 2
    assert "COROOT_BASE_URL" in capsys.readouterr().err


def test_transport_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COROOT_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("COROOT_USERNAME", "admin")
    monkeypatch.setenv("COROOT_PASSWORD", "pw")
    calls: list[dict[str, Any]] = []

    class FakeServer:
        def run(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr("mcp_coroot.cli.build_server", lambda settings: FakeServer())

    assert main([]) == 0
    assert calls[-1] == {"transport": "stdio"}

    assert (
        main(["--transport", "http", "--host", "0.0.0.0", "--port", "9", "--stateless"])
        == 0
    )
    assert calls[-1] == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 9,
        "streamable_http_path": "/mcp",
        "stateless_http": True,
        "json_response": False,
    }
