# Deploy

This is a static site. GitHub Pages serves the repo root (`index.html` redirects to `prototype/`), so any push to `main` deploys.

## One-line deploy

```
git push origin main
```

After the first push, enable Pages once: **Settings → Pages → Source: Deploy from a branch → Branch: `main` / `/ (root)`**. Live URL: `https://ghanemja.github.io/inbox-zero-board/`.

## First-time repo setup

If the GitHub remote doesn't exist yet:

```
gh repo create ghanemja/inbox-zero-board --public --source=. --push
```

## Config

- No build step. No Jekyll (`.nojekyll` is present so files starting with `_` aren't ignored).
- `prototype/index.html` is self-contained — vanilla JS + Tailwind via CDN. Loads `data.json` if present, otherwise falls back to seed data baked into the page.
- No backend is deployed from this repo. The `backend/` directory is local-only (see `backend/README.md`).

## Portfolio env

This repo has no backend → no env vars to set. See [`PORTFOLIO_ENV.md` in brain-university](https://github.com/ghanemja/brain-university/blob/main/PORTFOLIO_ENV.md) for the shared env-var pattern used by the backend-bearing projects in the portfolio.
