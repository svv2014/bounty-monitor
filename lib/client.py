"""
Minimal Python client for the Bounty Monitor API.

Usage:
    from lib.client import BountyClient

    client = BountyClient("http://localhost:18792")
    client.report(project="my-project", role="builder", event_type="working")
    client.report(project="my-project", role="builder", event_type="done")
    client.verdict(project="my-project", role="builder", points=5, reason="Clean merge.")
"""

from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
from typing import Any, Optional


class BountyClient:
    def __init__(
        self,
        base_url: str = "http://localhost:18792",
        timeout: float = 3.0,
        async_fire: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.async_fire = async_fire

    def _post(self, path: str, payload: dict) -> None:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except Exception:
            pass  # fire-and-forget — never raise

    def _send(self, path: str, payload: dict) -> None:
        if self.async_fire:
            t = threading.Thread(target=self._post, args=(path, payload), daemon=True)
            t.start()
        else:
            self._post(path, payload)

    def report(
        self,
        project: str,
        role: str,
        event_type: str,
        model: Optional[str] = None,
        payload: Optional[Any] = None,
    ) -> None:
        body: dict = {"project": project, "role": role, "event_type": event_type}
        if model is not None:
            body["model"] = model
        if payload is not None:
            body["payload"] = payload
        self._send("/api/report", body)

    def verdict(
        self,
        project: str,
        role: str,
        points: int,
        model: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        body: dict = {"project": project, "role": role, "points": points}
        if model is not None:
            body["model"] = model
        if reason is not None:
            body["reason"] = reason
        self._send("/api/verdict", body)
