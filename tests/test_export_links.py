"""Test de static/js/export_links.js dans un vrai navigateur (Playwright, page simulée).

La page est servie par interception de https://www.tiktok.com/@alice : aucun trafic réseau réel.
Ignoré (skip) si Playwright ou Chrome/Edge n'est pas disponible. Le vrai DOM de TikTok n'a pas
pu être vérifié : le script ne se fie qu'aux ancres href.
"""
import os
import time

import pytest

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "static", "js", "export_links.js")

PROFILE_URL = "https://www.tiktok.com/@alice"

# Page simulée : 3 liens au départ ; chaque défilement (qui change la position) ajoute un lot de
# liens ET agrandit la page, comme le chargement paresseux de TikTok. Au bout de 4 lots, plus rien.
FAKE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>fake</title>
<style>body{margin:0} #spacer{height:3000px}</style></head><body>
<div id="grid">
  <a href="/@alice/video/7000000000000000001?is_from_webapp=1">v1</a>
  <a href="https://www.tiktok.com/@Alice/video/7000000000000000002">v2 (casse)</a>
  <a href="/@alice/photo/7000000000000000003">p3</a>
  <a href="/@alice/video/7000000000000000001">doublon de v1</a>
</div>
<div id="suggestions">
  <a href="/@bob/video/7000000000000000099">autre pseudo</a>
  <a href="https://www.tiktok.com/@carol/photo/7000000000000000098">autre pseudo (photo)</a>
  <a href="/@alicia/video/7000000000000000097">pseudo proche</a>
  <a href="/@alice/video/not-a-number">pas un id</a>
  <a href="/@alice">profil</a>
</div>
<div id="spacer"></div>
<script>
  let batches = 0;
  window.addEventListener('scroll', () => {
    if (batches >= 4) return;
    const n = batches++;
    const grid = document.getElementById('grid');
    for (let i = 0; i < 3; i++) {
      const id = '70000000000' + String(10000 + n * 10 + i);  // chaîne : pas de perte de précision
      grid.insertAdjacentHTML('beforeend',
        `<a href="/@alice/${i === 2 ? 'photo' : 'video'}/${id}?lang=fr">new</a>`);
    }
    // un lien d'un autre pseudo et un doublon à chaque lot
    grid.insertAdjacentHTML('beforeend',
      `<a href="/@bob/video/${7000000000001000 + n}">bob</a><a href="/@alice/video/7000000000000000001">dup</a>`);
    document.getElementById('spacer').style.height = (3000 + (n + 1) * 1500) + 'px';
  });
</script></body></html>"""

EXPECTED_IDS = (
    ["7000000000000000001", "7000000000000000002", "7000000000000000003"]
    + [f"70000000000{10000 + n * 10 + i}" for n in range(4) for i in range(3)]
)


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        last_error = None
        for channel in ("chrome", "msedge"):
            try:
                instance = p.chromium.launch(channel=channel, headless=True)
                break
            except Exception as e:  # navigateur absent
                last_error = e
        else:
            pytest.skip(f"Chrome/Edge indisponible pour Playwright : {last_error}")
        yield instance
        instance.close()


def _new_page(browser, html=FAKE_PAGE, url=PROFILE_URL):
    context = browser.new_context(accept_downloads=True)
    try:
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://www.tiktok.com")
    except Exception:
        pass
    context.route("https://www.tiktok.com/**",
                  lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))
    page = context.new_page()
    page.goto(url)
    return context, page


def _script_expression():
    with open(SCRIPT_PATH, encoding="utf-8") as fh:
        return fh.read().strip().rstrip(";")


def _run_export(page, **options):
    page.evaluate("opts => { window.EXPORT_LIENS_OPTIONS = opts; }",
                  {"stepMs": 150, "idleMs": 900, "maxMs": 20000, **options})
    with page.expect_download(timeout=30000) as info:
        page.evaluate(_script_expression())
    return info.value


def test_export_collects_filters_and_downloads(browser, tmp_path):
    context, page = _new_page(browser)
    try:
        logs = []
        page.on("console", lambda m: logs.append(m.text))
        started = time.time()
        download = _run_export(page)
        assert download.suggested_filename == "tiktok_liens_alice.txt"
        target = tmp_path / "out.txt"
        download.save_as(str(target))
        lines = target.read_text(encoding="utf-8").splitlines()

        # filtrage par pseudo + normalisation (casse du pseudo de l'ancre conservée pour v2)
        ids = [l.rsplit("/", 1)[1] for l in lines]
        assert ids == EXPECTED_IDS
        assert len(set(lines)) == len(lines)                      # dédoublonnage
        assert all(l.startswith("https://www.tiktok.com/@") for l in lines)
        assert all("?" not in l for l in lines)                  # paramètres retirés
        assert not any("@bob" in l or "@carol" in l or "@alicia" in l for l in lines)
        assert "https://www.tiktok.com/@alice/photo/7000000000000000003" in lines
        assert "https://www.tiktok.com/@Alice/video/7000000000000000002" in lines

        # arrêt par inactivité (et non par le plafond de 20 s) + compteur dans la console
        assert time.time() - started < 15
        page.wait_for_function("window.__exportLiens")
        page.wait_for_timeout(200)  # laisse arriver les derniers messages de console
        assert any("liens trouvés pour @alice" in t for t in logs)
        assert any(t.startswith("Terminé : 15 liens") for t in logs)
        assert page.evaluate("window.__exportLiens") == {"pseudo": "alice", "total": 15}
    finally:
        context.close()


def test_clipboard_receives_same_text(browser, tmp_path):
    context, page = _new_page(browser)
    try:
        download = _run_export(page)
        target = tmp_path / "out.txt"
        download.save_as(str(target))
        try:
            clip = page.evaluate("navigator.clipboard.readText()")
        except Exception:
            pytest.skip("lecture du presse-papiers non autorisée dans ce navigateur")
        assert clip.splitlines() == target.read_text(encoding="utf-8").splitlines()
    finally:
        context.close()


def test_stops_at_max_duration_even_if_links_keep_coming(browser, tmp_path):
    # page où chaque défilement ajoute toujours un lien : seul le plafond maxMs peut arrêter
    endless = FAKE_PAGE.replace("if (batches >= 4) return;", "").replace(
        "String(10000 + n * 10 + i)", "String(50000 + n * 10 + i)")
    context, page = _new_page(browser, html=endless)
    try:
        started = time.time()
        download = _run_export(page, idleMs=60000, maxMs=2500)
        elapsed = time.time() - started
        assert 2 <= elapsed < 15
        target = tmp_path / "out.txt"
        download.save_as(str(target))
        assert len(target.read_text(encoding="utf-8").splitlines()) >= 3
    finally:
        context.close()


def test_refuses_outside_a_profile_page(browser):
    context, page = _new_page(browser, url="https://www.tiktok.com/foryou")
    try:
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        downloads = []
        page.on("download", lambda d: downloads.append(d))
        page.evaluate("opts => { window.EXPORT_LIENS_OPTIONS = opts; }", {"stepMs": 100, "idleMs": 300})
        page.evaluate(_script_expression())
        page.wait_for_timeout(500)
        assert downloads == []
        assert any("profil" in e for e in errors)
    finally:
        context.close()
