"""App shell must be revalidated on every load so a deploy never mixes old and new files."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("path", ["/", "/style.css", "/screens.js", "/sw.js"])
def test_app_shell_is_revalidated(client: TestClient, path: str):
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers.get("etag")  # so revalidation is a cheap 304
