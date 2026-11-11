# Website and interactive demo

**Live site:** <https://cxy2696.github.io/GitHub-Community-Bot/>

The site is a static page served from this `docs/` directory by GitHub Pages. It has
no build step, no analytics and no external CDN. It includes:

- a product tour written in plain HTML/CSS;
- an **interactive browser demo** with scripted replies in English, 中文 and 日本語;
- platform, feature and quickstart sections;
- links to the repository, documentation and privacy policy.

## Try the demo

1. Open <https://cxy2696.github.io/GitHub-Community-Bot/>.
2. Scroll to **Try the bot without installing anything**.
3. Try `!help`, `!link alice`, `!challenge`, `!leaderboard`, `!sentiment this is a
   terrible idea`, `!ask how do I review my first PR?`.
4. Use `!language zh` or `!language ja`, or the EN / 中文 / 日本語 buttons.

The demo is deliberately honest about what it is: a **simulation**. It does not call
Ollama, use a token, store data or contact the GitHub API. It exists so people can
feel the interaction before installing anything.

## Run the site locally

```bash
make demo
# open http://127.0.0.1:8000/
```

Or without Make:

```bash
python3 -m http.server 8000 -d docs
```

## Run the real bot

The browser demo is not the product. To use the real engine, database and local model:

```bash
ollama pull qwen2.5:3b
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
HTTP_ENABLED=false python -m github_community_bot --cli
```

The CLI uses the same command engine as Discord, Slack, Telegram and Matrix. There is
no fake path in production.

## Assets

| File | Purpose |
| --- | --- |
| `docs/index.html` | landing page |
| `docs/assets/site.css` | responsive design, no framework |
| `docs/assets/demo.js` | interactive demo; safe text rendering, localStorage language |
| `docs/assets/mark.svg` | logo and favicon |
| `docs/assets/demo.gif` | README animation |
| `docs/assets/demo-poster.png` | static poster / screenshot |
| `docs/assets/og-image.png` | Open Graph / social preview |

The demo data is intentionally in `demo.js` rather than fetched from the Python locale
catalogs, because GitHub Pages cannot run the bot. Keep both in sync when changing
user-facing wording; the demo only needs the main commands.

## Regenerating screenshots

The PNG/GIF assets were captured with Playwright. If you change the page:

```bash
pip install -e ".[demo]"
playwright install chromium
python scripts/render_demo_assets.py
```

The script starts its own local server, drives the page, and writes all three assets.
It uses a 1180 px viewport for the GIF, a 1200×630 composition for `og-image.png`,
and an adaptive 128-colour GIF palette. Browsers are optional; they are not needed to
run the bot or the test suite.

## Accessibility notes

- Landmarks, a skip link, focus-visible outlines and semantic headings.
- The chat log uses `role="log"` and `aria-live="polite"`.
- Decorative images have empty `alt` text; the demo animation has descriptive alt text.
- `prefers-reduced-motion` disables animation.
- Type is system-font based; the page works without web fonts.

## Deployment

GitHub Pages is configured to serve `main` → `/docs`. To update the site, merge a
change to `docs/` on `main`; Pages rebuilds automatically. `docs/.nojekyll` prevents
Jekyll from processing the static assets.

If the repository is renamed again, update:

- `og:url` and `og:image` in `docs/index.html`;
- the GitHub links in `docs/index.html` and this file;
- the `homepage` field in `pyproject.toml`;
- the repository's **About → Website** URL in GitHub settings.
