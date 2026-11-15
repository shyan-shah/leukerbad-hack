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


def test_patient_screen_served(no_site):
    r = no_site.get("/screens/patient.html")
    assert r.status_code == 200
    assert "./common.js" in r.text and "./track.js" in r.text and "simBanner" in r.text
    assert "javascript" in no_site.get("/screens/track.js").headers["content-type"]


TRACK_CHECK = r"""
import { Track } from "./track.js";
const ok = (c, msg) => { if (!c) { console.error("FAIL " + msg); process.exit(1); } };
const near = (a, b) => Math.abs(a - b) < 1e-9;
const S = (t, x, phase = "out", tx = null) => ({ t, phase, pos: [0.45 + x, 0, 0.3], target: tx === null ? null : [0.45 + tx, 0, 0.3] });
let k = new Track(0.30);
let r = k.update(S(0, 0.0, "out"));
ok(r.s === null, "mid-rep open waits for rest");
r = k.update(S(1, 0.0, "idle"));
ok(near(r.s, 0), "start at rest is 0");
r = k.update(S(2, 0.15, "out", 0.20));
ok(near(r.s, 0.5) && near(r.targetS, 0.2 / 0.3), "half reach and target ahead");
r = k.update(S(3, 0.36));
ok(near(r.s, 1), "track grows past min length");
r = k.update(S(0.1, 0.0, "idle"));
ok(near(r.s, 0) && near(k.len, 0.30), "new session resets");
k = new Track(0.30);
k.update({ t: 0, phase: "idle", pos: [0, 0.5, 0] });
r = k.update({ t: 1, phase: "out", pos: [0.001, 0.35, 0] });
ok(k.axis === 1 && k.sign === -1 && near(r.s, 0.5), "detects axis y, negative direction");
k = new Track(0.28);
r = k.update(S(0, 0.0, "setup"));
ok(near(r.s, 0), "pull: the setup phase is a valid start");
r = k.update(S(1, 0.28, "setup"));
ok(near(r.s, 1), "pull: setup ends at the far end");
r = k.update(S(2, 0.14, "out"));
ok(near(r.s, 0.5), "pull: reps come back along the same line");
console.log("ok");
"""


def test_track_geometry_with_node(tmp_path):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    shutil.copy(SCREENS / "track.js", tmp_path / "track.js")
    (tmp_path / "check.mjs").write_text(TRACK_CHECK, encoding="utf-8")
    p = subprocess.run([node, str(tmp_path / "check.mjs")], capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and "ok" in p.stdout, p.stdout + p.stderr


def test_patient_screen_knows_the_exercises():
    html = (SCREENS / "patient.html").read_text(encoding="utf-8")
    for text in ("Move the handle to the far end", "Push and hold", "Best try", "/api/exercises",
                 'r.mode === "isometric"', "m.exercise"):
        assert text in html
    js = (SCREENS / "common.js").read_text(encoding="utf-8")
    assert "export function modeClass" in js


def test_patient_app_served_at_app(no_site):
    """Mat and Gio's app (demo/app) is served at /app/ so it shares an origin with the API."""
    r = no_site.get("/app/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert no_site.get("/api/health").status_code == 200          # API not shadowed
    assert no_site.get("/screens/index.html").status_code == 200  # screens not shadowed


@pytest.mark.parametrize("page,files", [
    ("physio", ("physio.js", "physio.css")),
    ("operator", ("operator.js", "operator.css")),
])
def test_physio_and_operator_screens_served(no_site, page, files):
    r = no_site.get(f"/screens/{page}.html")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Vita" in r.text and "style.css" in r.text
    for f in files:
        got = no_site.get(f"/screens/{f}")
        assert got.status_code == 200
        assert ("javascript" if f.endswith(".js") else "text/css") in got.headers["content-type"]
        assert f in r.text


def test_operator_hold_does_not_depend_on_the_module():
    """HOLD and the Space bar are wired in a plain script in the page, before the module loads."""
    html = (SCREENS / "operator.html").read_text(encoding="utf-8")
    plain = html.split("<script>", 1)[1].split("</script>", 1)[0]
    assert "/api/hold" in plain and '"Space"' in plain and "import" not in plain
    assert html.index("<script>") < html.index('<script type="module"')
    assert "/api/hold" not in (SCREENS / "operator.js").read_text(encoding="utf-8")


def test_physio_charts_carry_a_simulated_label():
    js = (SCREENS / "physio.js").read_text(encoding="utf-8")
    assert "simtag" in js and '"SIMULATED"' in js and "not clinically validated" in js


def test_calibration_wording_on_screens(no_site):
    patient = no_site.get("/screens/patient.html").text
    assert "Push once at a level that feels comfortable" in patient and "Resistance set: " in patient
    assert "calibration" in patient and "arming" in patient
    op = no_site.get("/screens/operator.html").text + no_site.get("/screens/operator.js").text
    assert "Push once at a level that feels comfortable" in op and "Resistance set: " in op
    assert 'id="go"' in op and 'id="resume"' in op and "/api/session/resume" in op
    for name in ("patient.html", "operator.html", "operator.js", "physio.html", "physio.js", "index.html"):
        text = no_site.get(f"/screens/{name}").text
        assert not re.search(r"\bAI\b", text) and "machine learning" not in text.lower(), name
