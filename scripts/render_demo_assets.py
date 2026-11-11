#!/usr/bin/env python3
"""Regenerate the website's demo GIF, poster and Open Graph image.

Requires the optional demo dependencies and a Chromium build:

    pip install -e ".[demo]"
    playwright install chromium
    python scripts/render_demo_assets.py

The script serves docs/ locally, drives the real page with Playwright, and writes
docs/assets/demo.gif, demo-poster.png and og-image.png. It is intentionally not part
of the test suite because it needs a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def start_server(port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(QuietHandler, directory=str(DOCS))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    return server


async def capture(base_url: str) -> tuple[list[bytes], bytes, bytes]:
    from playwright.async_api import async_playwright

    frames: list[bytes] = []
    poster = b""
    og = b""
    async with async_playwright() as p:
        try:
            # The full Chromium build is more reliable than the headless shell
            # for animated element screenshots.
            browser = await p.chromium.launch(
                channel="chromium", args=["--no-sandbox", "--disable-gpu"]
            )
        except Exception:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        page = await browser.new_page(viewport={"width": 1180, "height": 820})
        await page.goto(base_url, wait_until="networkidle")
        await page.wait_for_timeout(700)
        demo = page.locator("#demo-shell")
        frames.append(await demo.screenshot())

        await page.locator("[data-prompt='!link alice']").click()
        await page.wait_for_timeout(1200)
        frames.append(await demo.screenshot())

        await page.locator("[data-prompt='!challenge']").click()
        await page.wait_for_timeout(1200)
        poster = await demo.screenshot()
        frames.append(poster)

        await page.locator("[data-demo-lang='zh']").click()
        await page.locator("[data-prompt='!help']").click()
        await page.wait_for_timeout(1200)
        frames.append(await demo.screenshot())

        await page.locator("[data-demo-lang='ja']").click()
        await page.locator("[data-prompt='!leaderboard']").click()
        await page.wait_for_timeout(1200)
        frames.append(await demo.screenshot())

        og_page = await browser.new_page(viewport={"width": 1200, "height": 630})
        await og_page.goto(base_url, wait_until="networkidle")
        await og_page.add_style_tag(
            content="""
            .hero { padding-top: 34px; padding-bottom: 0; gap: 26px; align-items: start; }
            .hero h1 { font-size: 52px; margin-bottom: 16px; }
            .hero .lede { font-size: 15px; margin-bottom: 18px; }
            .hero .cta-row { margin-bottom: 0; }
            .hero .hero-points { display: none; }
            .terminal { transform: rotate(-.5deg) scale(.94); transform-origin: top left; }
            """
        )
        await og_page.wait_for_timeout(500)
        og = await og_page.screenshot()
        await browser.close()
    return frames, poster, og


def write_assets(frames: list[bytes], poster: bytes, og: bytes) -> None:
    from io import BytesIO

    from PIL import Image

    ASSETS.mkdir(parents=True, exist_ok=True)
    images = []
    for data in frames:
        image = Image.open(BytesIO(data)).convert("RGB")
        image.thumbnail((900, 900), Image.LANCZOS)
        images.append(image)
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    gif_frames = []
    for image in images:
        canvas = Image.new("RGB", (width, height), (10, 15, 27))
        canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        gif_frames.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    gif_frames[0].save(
        ASSETS / "demo.gif",
        save_all=True,
        append_images=gif_frames[1:],
        duration=[1500, 1700, 2000, 2200, 2200],
        loop=0,
        optimize=True,
        disposal=2,
    )

    poster_image = Image.open(BytesIO(poster)).convert("RGB")
    poster_image.thumbnail((1200, 1200), Image.LANCZOS)
    poster_image.save(ASSETS / "demo-poster.png", optimize=True)

    og_image = Image.open(BytesIO(og)).convert("RGB").resize((1200, 630), Image.LANCZOS)
    og_image.save(ASSETS / "og-image.png", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8907)
    args = parser.parse_args()

    try:
        import playwright  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            'Missing demo dependencies. Run: pip install -e ".[demo]" && playwright install chromium'
        ) from exc

    if not (DOCS / "index.html").exists():
        raise SystemExit(f"Website not found at {DOCS / 'index.html'}")

    server = start_server(args.port)
    try:
        frames, poster, og = asyncio.run(capture(f"http://127.0.0.1:{args.port}/"))
        write_assets(frames, poster, og)
    finally:
        server.shutdown()
        server.server_close()
    print(f"Updated {ASSETS / 'demo.gif'}")
    print(f"Updated {ASSETS / 'demo-poster.png'}")
    print(f"Updated {ASSETS / 'og-image.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
