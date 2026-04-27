"""Verify the application pipeline API entrypoint against real PostgreSQL."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.api.app import create_app
from src.config import (
    get_database_env_snapshot,
    probe_database_connection,
    probe_database_environment,
    probe_pgvector_extension,
)

API_KEY = "dn-dev-key-change-in-production"
ENDPOINT = "/api/v1/application/pipeline/run"


def assert_pass(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  [PASS] {message}")


def print_info(message: str) -> None:
    print(f"  [INFO] {message}")


def fail_with_layer(layer: str, detail: str) -> None:
    print(f"  [FAIL] Layer: {layer}")
    print(f"  [FAIL] Detail: {detail}")
    raise SystemExit(1)


def ensure_postgresql_ready() -> None:
    print_info(f"DB env snapshot: {get_database_env_snapshot()}")

    environment_probe = probe_database_environment()
    if not environment_probe.ok:
        fail_with_layer(environment_probe.layer, environment_probe.detail)
    print_info(environment_probe.detail)

    connection_probe = probe_database_connection()
    if not connection_probe.ok:
        fail_with_layer(connection_probe.layer, connection_probe.detail)
    print_info(connection_probe.detail)

    pgvector_probe = probe_pgvector_extension()
    if not pgvector_probe.ok:
        fail_with_layer(pgvector_probe.layer, pgvector_probe.detail)
    print_info(pgvector_probe.detail)


def build_document(title: str, url: str, content_text: str) -> dict[str, str]:
    return {
        "title": title,
        "source_type": "blog",
        "url": url,
        "author": "Example Author",
        "language": "en",
        "content_text": content_text,
    }


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def running_server(extra_env: dict[str, str] | None = None):
    port = find_free_port()
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_for_server(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def wait_for_server(base_url: str) -> None:
    deadline = time.time() + 20
    health_url = f"{base_url}/api/v1/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    fail_with_layer("API call", "Timed out waiting for local API server to start")


def post_json(
    base_url: str,
    path: str,
    payload: dict[str, object],
    api_key: str | None = API_KEY,
) -> tuple[int, dict[str, object]]:
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["X-API-Key"] = api_key

    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_application_route_registered() -> None:
    app = create_app()
    routes = [route.path for route in app.routes if hasattr(route, "path")]
    assert_pass(ENDPOINT in routes, "application pipeline route is registered")


def test_single_document_process_only(base_url: str) -> None:
    status_code, payload = post_json(
        base_url,
        ENDPOINT,
        {
            "document": build_document(
                title="API single document process-only",
                url=f"https://example.com/api-process-only?run_id={uuid4().hex}",
                content_text="OpenAI and Anthropic appear in this API process-only verification document.",
            ),
            "persist": False,
            "include_daily_brief": True,
        },
    )

    assert_pass(status_code == 200, "API persist=false request succeeds")
    assert_pass(payload["success"] is True, "API persist=false returns success=true")
    assert_pass(payload["persisted"] is None, "API persist=false keeps persisted as null")
    assert_pass(payload["summary_info"]["daily_brief_generated"] is True, "API persist=false still generates daily brief")
    assert_pass(
        sorted(payload.keys()) == ["document_id", "error", "persisted", "success", "summary_info"],
        "API response keeps CLI-like minimal result shape",
    )


def test_validation_error_missing_content_text(base_url: str) -> None:
    status_code, payload = post_json(
        base_url,
        ENDPOINT,
        {
            "document": {
                "title": "API validation missing content_text",
                "source_type": "blog",
                "url": f"https://example.com/api-validation-missing-content?run_id={uuid4().hex}",
                "author": "Example Author",
                "language": "en",
            },
            "persist": False,
            "include_daily_brief": True,
        },
    )

    assert_pass(status_code == 422, "missing document.content_text returns 422")
    assert_pass(isinstance(payload.get("detail"), list), "422 response keeps FastAPI validation detail list")
    assert_pass(
        any(item.get("loc") == ["body", "document", "content_text"] for item in payload["detail"]),
        "422 validation detail points to document.content_text",
    )


def test_missing_api_key_returns_401(base_url: str) -> None:
    status_code, payload = post_json(
        base_url,
        ENDPOINT,
        {
            "document": build_document(
                title="API missing key",
                url=f"https://example.com/api-missing-key?run_id={uuid4().hex}",
                content_text="This request intentionally omits the API key header.",
            ),
            "persist": False,
        },
        api_key=None,
    )

    assert_pass(status_code == 401, "missing X-API-Key returns 401")
    assert_pass(payload["detail"]["error_code"] == "missing_api_key", "missing key response uses auth missing_api_key code")


def test_invalid_api_key_returns_401(base_url: str) -> None:
    status_code, payload = post_json(
        base_url,
        ENDPOINT,
        {
            "document": build_document(
                title="API invalid key",
                url=f"https://example.com/api-invalid-key?run_id={uuid4().hex}",
                content_text="This request intentionally uses the wrong API key header.",
            ),
            "persist": False,
        },
        api_key="dn-invalid-key",
    )

    assert_pass(status_code == 401, "invalid X-API-Key returns 401")
    assert_pass(payload["detail"]["error_code"] == "invalid_api_key", "invalid key response uses auth invalid_api_key code")


def test_single_document_persist_without_daily_brief(base_url: str) -> None:
    status_code, payload = post_json(
        base_url,
        ENDPOINT,
        {
            "document": build_document(
                title="API persist no daily brief",
                url=f"https://example.com/api-persist-no-brief?run_id={uuid4().hex}",
                content_text="This API persistence verification disables daily brief generation explicitly.",
            ),
            "persist": True,
            "include_daily_brief": False,
        },
    )

    assert_pass(status_code == 200, "API persist=true without daily brief succeeds")
    assert_pass(payload["success"] is True, "API persist=true without daily brief returns success=true")
    assert_pass(payload["persisted"] is not None, "API persist=true returns persisted artifacts")
    assert_pass(
        payload["summary_info"]["daily_brief_generated"] is False,
        "API persist=true without daily brief reflects disabled daily brief",
    )


def test_single_document_persist_with_default_daily_brief(base_url: str) -> None:
    status_code, payload = post_json(
        base_url,
        ENDPOINT,
        {
            "document": build_document(
                title="API persist with daily brief",
                url=f"https://example.com/api-persist-default-brief?run_id={uuid4().hex}",
                content_text="This API persistence verification uses the default daily brief path.",
            ),
            "persist": True,
        },
    )

    if status_code != 200:
        fail_with_layer("API call", f"persist=true default path returned HTTP {status_code}: {json.dumps(payload)}")

    assert_pass(payload["success"] is True, "API persist=true with default daily brief returns success=true")
    assert_pass(payload["persisted"] is not None, "API persist=true with default daily brief returns persisted artifacts")
    assert_pass(
        payload["summary_info"]["daily_brief_generated"] is True,
        "API persist=true with default daily brief reports generated daily brief",
    )


def test_persist_failure_returns_structured_500() -> None:
    failing_db_env = {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "1",
        "DB_NAME": "daily_news",
        "DB_USER": "postgres",
        "DB_PASSWORD": "postgres",
    }

    with running_server(extra_env=failing_db_env) as base_url:
        status_code, payload = post_json(
            base_url,
            ENDPOINT,
            {
                "document": build_document(
                    title="API persist failure path",
                    url=f"https://example.com/api-persist-failure?run_id={uuid4().hex}",
                    content_text="This request forces the persistence path to fail so the API 500 behavior can be verified.",
                ),
                "persist": True,
                "include_daily_brief": False,
            },
        )

    payload_text = json.dumps(payload).lower()
    assert_pass(status_code == 500, "persistence failure returns 500")
    assert_pass(payload["success"] is False, "500 response returns success=false")
    assert_pass(isinstance(payload.get("error"), str) and payload["error"], "500 response includes minimal error string")
    assert_pass("traceback" not in payload_text, "500 response body does not expose traceback text")
    assert_pass(payload.get("document_id") is None, "500 response keeps document_id as null")
    assert_pass(payload.get("summary_info") is None, "500 response keeps summary_info as null")


def main() -> None:
    print("=" * 60)
    print("Application API verification")
    print("=" * 60)
    ensure_postgresql_ready()
    test_application_route_registered()
    try:
        with running_server() as base_url:
            test_single_document_process_only(base_url)
            test_validation_error_missing_content_text(base_url)
            test_missing_api_key_returns_401(base_url)
            test_invalid_api_key_returns_401(base_url)
            test_single_document_persist_without_daily_brief(base_url)
            test_single_document_persist_with_default_daily_brief(base_url)
        test_persist_failure_returns_structured_500()
    except AssertionError as exc:
        fail_with_layer("API call", str(exc))

    print("=" * 60)
    print("Application API verification passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
