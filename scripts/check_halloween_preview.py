"""Browser review against the isolated local preview server; writes are intercepted."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = os.environ.get("CINEMA_PREVIEW_URL", "http://127.0.0.1:8013")
assert urlparse(BASE).hostname in {"127.0.0.1", "localhost"}, "Only run against a local server."
OUT = Path(__file__).resolve().parents[1] / ".local" / "halloween"
OUT.mkdir(parents=True, exist_ok=True)


def check_layout(page):
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    for button in page.locator("button, .preview-notice a").all():
        if button.is_visible():
            box = button.bounding_box()
            assert box["width"] >= 43.9 and box["height"] >= 43.9, (button.get_attribute("class"), box)


def screenshot(page, name):
    for close in page.locator(".toast__x").all():
        close.click()
    page.evaluate("document.fonts.ready")
    # Decode all images and paint the offscreen blend layers before full-page capture.
    page.evaluate("Promise.all([...document.images].filter(i=>i.complete&&i.naturalWidth).map(i=>i.decode().catch(()=>{})))")
    for selector in [".halloween-portrait--nosferatu", ".halloween-divider"]:
        page.locator(selector).scroll_into_view_if_needed()
        page.wait_for_timeout(150)
    page.evaluate("scrollTo(0,0)")
    page.mouse.move(0, 0)
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / name), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in ([] if "--admin-only" in sys.argv else [1440, 768, 390, 320]):
        context = browser.new_context(viewport={"width": width, "height": 1000 if width > 800 else 844}, service_workers="block")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for stage in ["winner", "submissions", "voting"]:
            print("Reviewing", width, stage, flush=True)
            page.goto(f"{BASE}/preview?theme=halloween&stage={stage}", wait_until="networkidle")
            page.locator(".halloween-portrait--phantom").wait_for()
            check_layout(page)
            assert page.locator("#films .film-card").count() == 4
            assert page.locator("[data-halloween-decoration]").count() == 4
            assert page.locator(".preview-notice").is_visible()
            assert page.evaluate("[...document.querySelectorAll('.halloween-portrait img,#films img')].every(i=>i.complete&&i.naturalWidth>0)")
            if stage == "winner":
                page.locator(".feature-image").wait_for()
                assert page.locator("#heroTitle").inner_text() == "Alien"
                assert "AmR3JG1VQVxU8TfAvljUhfSFUOx" in page.locator(".feature-image").get_attribute("src")
                page.locator(".feature-action").first.click()
                page.locator("#movieDetailsDialog").wait_for(state="visible")
                assert page.locator("#movieDetailsTitle").inner_text() == "Alien"
                page.keyboard.press("Escape")
                assert not page.locator("#movieDetailsDialog").evaluate("e=>e.open")
            elif stage == "submissions":
                page.locator("#openSubmission").click()
                assert page.locator("#submissionDialog").evaluate("e=>e.open")
                page.keyboard.press("Escape")
                assert not page.locator("#submissionDialog").evaluate("e=>e.open")
            else:
                page.locator(".film-actions button").first.click()
                assert page.locator("#authModal .hof-modal__panel").is_visible()
                page.keyboard.press("Escape")
            page.locator("#btnChat").click()
            assert page.locator("#chatPanel").evaluate("e=>e.classList.contains('chat-panel--open')")
            page.keyboard.press("Escape")
            assert page.locator("#btnChat").evaluate("e=>e===document.activeElement")
            page.locator(".reaction-add-btn").first.click()
            assert page.locator(".reaction-picker--open").count() == 1
            page.locator(".reaction-picker__btn").first.click()
            page.locator("#authClose").click()
            page.locator("#authModal .hof-modal__panel").wait_for(state="hidden")
            page.locator("#btnLogin").press("Enter")
            page.locator("#authModal .hof-modal__panel").wait_for(state="visible")
            page.locator("#authClose").click()
            assert page.locator("#btnLogin").evaluate("e=>e===document.activeElement")
            screenshot(page, f"{stage}-{width}.png")
            page.locator("#btnTheme").click()
            assert page.locator("html").get_attribute("data-theme") == "dark"
            check_layout(page)
            screenshot(page, f"{stage}-dark-{width}.png")
            page.locator("#btnTheme").click()
        # Same document: theme switches remove all prior decorations, including reset.
        for theme in ["italian", "netflix", "halloween", "", "halloween", "italian", ""]:
            page.evaluate("t=>applyTheme(t)", theme)
            assert page.locator("[data-halloween-decoration]").count() == (4 if theme == "halloween" else 0)
            assert page.locator(".it-flag-left,.it-flag-right").count() == (2 if theme == "italian" else 0)
            assert page.locator(".netflix-brand-mark").count() == (1 if theme == "netflix" else 0)
            assert page.evaluate("document.body.classList.contains('theme-halloween')") == (theme == "halloween")
            if theme != "italian":
                assert not page.locator("#itWhyBtn").is_visible()
        assert not errors, errors
        context.close()
        print(width, "px: images, layouts, dialogs, keyboard, chat, reactions, light/dark and theme cleanup passed")

    # Reduced motion disables the 67 animation but preserves its stationary hit area.
    context = browser.new_context(reduced_motion="reduce", service_workers="block")
    page = context.new_page()
    page.goto(f"{BASE}/preview?theme=halloween", wait_until="networkidle")
    page.locator(".club-emblem").hover()
    page.wait_for_timeout(500)
    assert page.locator(".emblem-motion").evaluate_all("digits=>digits.every(d=>d.getAnimations().length===0)")
    context.close()
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.goto(f"{BASE}/preview?theme=halloween", wait_until="networkidle")
    before = page.locator(".club-emblem").bounding_box()
    page.locator(".club-emblem").hover()
    page.wait_for_timeout(450)
    assert page.locator(".emblem-motion").evaluate_all("digits=>digits.every(d=>d.getAnimations().length>0)")
    assert page.locator(".club-emblem").bounding_box() == before
    context.close()

    # Admin preview opens Halloween without submitting /admin/weeks.
    context = browser.new_context(service_workers="block")
    context.add_init_script("localStorage.setItem('cinema_club_token','browser-only')")
    page = context.new_page()
    page.route("**/auth/me", lambda r: r.fulfill(json={"id": 999, "username": "browser_admin", "is_admin": True}))
    page.route("**/admin/weeks/current", lambda r: r.fulfill(body="null", content_type="application/json"))
    page.route("**/admin/films/needs-review*", lambda r: r.fulfill(json=[]))
    page.route("**/admin/users*", lambda r: r.fulfill(json=[]))
    writes = []
    page.on("request", lambda r: writes.append(r.url) if r.method != "GET" else None)
    page.goto(f"{BASE}/admin", wait_until="networkidle")
    page.locator("#newWeekTheme").fill("halloween")
    with page.expect_popup() as popup:
        page.locator("#previewWeek").click()
    preview = popup.value
    preview.wait_for_load_state("networkidle")
    assert "theme=halloween" in preview.url
    assert preview.locator(".halloween-edition").is_visible()
    assert not writes, writes
    context.close()
    browser.close()
    print("67 motion, reduced motion and admin preview passed; no database writes")
