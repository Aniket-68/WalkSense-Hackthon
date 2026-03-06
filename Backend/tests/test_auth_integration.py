from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

import httpx
from fastapi import WebSocketDisconnect


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "Backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class _FakeWebSocket:
    def __init__(self, access_token: str = ""):
        self.query_params = {"access_token": access_token} if access_token else {}
        self.accepted = False
        self.closed_code = None
        self.sent_payloads = []

    async def close(self, code: int) -> None:
        self.closed_code = code

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload):
        self.sent_payloads.append(payload)
        # Stop server loop after first message for test determinism.
        raise WebSocketDisconnect(code=1000)


class AuthFlowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.auth_db = os.path.join(self.temp_dir.name, "auth_test.db")

        os.environ["APP_ENV"] = "development"
        os.environ["AUTH_DB_PATH"] = self.auth_db
        os.environ["AUTH_BOOTSTRAP_ENABLED"] = "true"
        os.environ["AUTH_BOOTSTRAP_USERNAME"] = "admin"
        os.environ["AUTH_BOOTSTRAP_PASSWORD"] = "TestPass_123!"
        os.environ["AUTH_BOOTSTRAP_FORCE_RESET"] = "true"
        os.environ["JWT_ACCESS_SECRET"] = "test-access-secret-1234567890"
        os.environ["JWT_REFRESH_SECRET"] = "test-refresh-secret-1234567890"
        os.environ["JWT_ACCESS_TTL_SECONDS"] = "120"
        os.environ["JWT_REFRESH_TTL_SECONDS"] = "3600"
        os.environ["AUTH_COOKIE_SECURE"] = "false"
        os.environ["AUTH_COOKIE_CROSS_SITE"] = "false"
        os.environ["AUTH_RATE_LIMIT_LOGIN_MAX_ATTEMPTS"] = "3"
        os.environ["AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS"] = "60"
        os.environ["AUTH_RATE_LIMIT_LOGIN_BLOCK_SECONDS"] = "120"
        os.environ["AUTH_RATE_LIMIT_REFRESH_MAX_ATTEMPTS"] = "4"
        os.environ["AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS"] = "60"
        os.environ["AUTH_RATE_LIMIT_REFRESH_BLOCK_SECONDS"] = "120"

        for mod in ("API.server", "API.auth"):
            if mod in sys.modules:
                del sys.modules[mod]

        self.server_mod = importlib.import_module("API.server")
        self.auth_mod = importlib.import_module("API.auth")

        self.transport = httpx.ASGITransport(app=self.server_mod.app)
        self.client = httpx.AsyncClient(
            transport=self.transport,
            base_url="http://test",
            follow_redirects=True,
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temp_dir.cleanup()

    async def _login(self) -> dict:
        response = await self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass_123!"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_login_refresh_logout_flow(self) -> None:
        login_data = await self._login()
        access = login_data["access_token"]
        self.assertTrue(access)

        me = await self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["username"], "admin")

        refresh = await self.client.post("/api/auth/refresh")
        self.assertEqual(refresh.status_code, 200, refresh.text)
        self.assertTrue(refresh.json()["access_token"])

        logout = await self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200, logout.text)

        refresh_after_logout = await self.client.post("/api/auth/refresh")
        self.assertEqual(refresh_after_logout.status_code, 401, refresh_after_logout.text)

    async def test_refresh_reuse_blacklists_family(self) -> None:
        await self._login()
        old_refresh = self.client.cookies.get("walksense_refresh_token")

        rotated = await self.client.post("/api/auth/refresh")
        self.assertEqual(rotated.status_code, 200, rotated.text)
        new_refresh = self.client.cookies.get("walksense_refresh_token")
        self.assertNotEqual(old_refresh, new_refresh)

        attacker = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.server_mod.app),
            base_url="http://test",
        )
        attacker.cookies.set("walksense_refresh_token", old_refresh, path="/api/auth")
        reuse = await attacker.post("/api/auth/refresh")
        await attacker.aclose()
        self.assertEqual(reuse.status_code, 401, reuse.text)
        self.assertEqual(reuse.json().get("status"), "compromised")

        self.client.cookies.set("walksense_refresh_token", new_refresh, path="/api/auth")
        blocked = await self.client.post("/api/auth/refresh")
        self.assertEqual(blocked.status_code, 401, blocked.text)

    async def test_ws_auth_rejection_and_acceptance(self) -> None:
        ws_denied = _FakeWebSocket(access_token="")
        await self.server_mod.websocket_endpoint(ws_denied)
        self.assertFalse(ws_denied.accepted)
        self.assertEqual(ws_denied.closed_code, 4401)

        access = (await self._login())["access_token"]
        ws_allowed = _FakeWebSocket(access_token=access)
        await self.server_mod.websocket_endpoint(ws_allowed)
        self.assertTrue(ws_allowed.accepted)
        self.assertGreaterEqual(len(ws_allowed.sent_payloads), 1)
        self.assertIn("system_status", ws_allowed.sent_payloads[0])

    async def test_login_rate_limit_blocks_bruteforce(self) -> None:
        for _ in range(3):
            failed = await self.client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong-password"},
            )
            self.assertEqual(failed.status_code, 401, failed.text)

        blocked = await self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        self.assertEqual(blocked.status_code, 429, blocked.text)

    async def test_metrics_endpoint_exposes_auth_metrics(self) -> None:
        await self._login()
        metrics = await self.client.get("/metrics/auth")
        self.assertEqual(metrics.status_code, 200, metrics.text)
        body = metrics.text
        self.assertIn("walksense_auth_audit_events_total", body)
        self.assertIn("walksense_auth_rate_limit_active_blocks", body)

    async def test_cleanup_retention_deletes_stale_rows(self) -> None:
        stale_ts = int(time.time()) - 9999
        conn = sqlite3.connect(self.auth_db)
        conn.execute(
            """
            INSERT INTO auth_audit_events
            (ts, event_type, success, username, user_id, family_id, jti, ip, detail)
            VALUES (?, 'test_event', 0, NULL, NULL, NULL, NULL, NULL, 'stale')
            """,
            (stale_ts,),
        )
        conn.execute(
            """
            INSERT INTO auth_rate_limits
            (action, identifier, window_started_at, fail_count, blocked_until)
            VALUES ('login', 'stale-id', ?, 2, NULL)
            """,
            (stale_ts,),
        )
        conn.commit()
        conn.close()

        result = self.auth_mod.cleanup_auth_tables(
            audit_retention_seconds=60,
            rate_limit_retention_seconds=60,
        )
        self.assertGreaterEqual(result["deleted_audit_events"], 1)
        self.assertGreaterEqual(result["deleted_rate_limits"], 1)


if __name__ == "__main__":
    unittest.main()
