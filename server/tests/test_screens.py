import re
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.api import create_app
from server.mock import MockArm, MockEngine

FAST = partial(MockEngine, strength=0.8, time_scale=200)
SCREENS = Path(__file__).resolve().parents[1] / "screens"


def _client(tmp_path, site_dir):
    return TestClient(create_app(MockArm, tmp_path / "s.db", engine_factory=FAST, site_dir=site_dir))


@pytest.fixture
def no_site(tmp_path):
    with _client(tmp_path, tmp_path / "nosite") as c:
        yield c


@pytest.fixture
def with_site(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>DEMO SITE</html>", encoding="utf-8")
    with _client(tmp_path, site) as c:
        yield c


@pytest.mark.parametrize("path,ctype", [
    ("/screens/index.html", "text/html"),
    ("/screens/", "text/html"),
    ("/screens/common.js", "javascript"),
    ("/screens/style.css", "text/css"),
])
def test_screens_served(no_site, path, ctype):
    r = no_site.get(path)
    assert r.status_code == 200
    assert ctype in r.headers["content-type"]


def test_root_without_site_is_404(no_site):
    assert no_site.get("/").status_code == 404


def test_site_still_served_and_screens_not_shadowed(with_site):
    assert "DEMO SITE" in with_site.get("/").text
    r = with_site.get("/screens/index.html")
    assert r.status_code == 200 and "DEMO SITE" not in r.text and "common.js" in r.text
    assert with_site.get("/screens/common.js").status_code == 200
    assert with_site.get("/api/health").json()["ok"] is True


def test_screens_have_no_external_urls():
    pat = re.compile(r"(https?:|wss?:)?//(?!127\.0\.0\.1|localhost|\$\{)[a-z0-9.-]+\.[a-z]{2,}", re.I)
    for f in SCREENS.iterdir():
        if f.suffix in {".html", ".js", ".css"}:
            assert not pat.search(f.read_text(encoding="utf-8")), f"external URL in {f.name}"
