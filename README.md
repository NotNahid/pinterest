# Pinterest Portfolio Sync

Automatically syncs a Pinterest board into a static gallery using GitHub Actions.

```
Pinterest Board → GitHub Actions (cron) → sync.py → images/ + works.json → index.html
```

---

## Setup

### 1. Get a Pinterest API token

1. Go to <https://developers.pinterest.com/> and create an app.
2. Request the **boards:read** and **pins:read** scopes.
3. Generate a user access token and copy it.

### 2. Add GitHub Secrets

In your repository go to **Settings → Secrets and variables → Actions** and add:

| Secret name            | Value                                              |
|------------------------|----------------------------------------------------|
| `PINTEREST_API_TOKEN`  | Your Pinterest user access token                   |
| `PINTEREST_USERNAME`   | Your Pinterest username (as it appears in the URL) |
| `PINTEREST_BOARD`      | Board slug — the last part of the board URL        |

**Finding the board slug:**  
The URL `https://pinterest.com/yourname/my-portfolio/` → slug is `my-portfolio`.

### 3. Push this repository to GitHub

```bash
git init
git add .
git commit -m "init: Pinterest portfolio sync"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 4. Enable GitHub Actions

Actions are enabled by default on public repos. For private repos, check **Settings → Actions → General**.

### 5. Run it

- **Automatic:** runs every 6 hours via cron.
- **Manual:** go to **Actions → Pinterest Portfolio Sync → Run workflow**.

---

## How it works

| File | Role |
|------|------|
| `scripts/sync.py` | Fetches the board via Pinterest API v5, downloads only new images, updates `works.json` |
| `.github/workflows/sync.yml` | Runs sync on schedule and commits any changes back to the repo |
| `works.json` | The "database" — one entry per synced pin |
| `images/` | Downloaded pin images |
| `index.html` | Static gallery that reads `works.json` at load time |

### works.json schema

```json
[
  {
    "pin_id":   "123456789",
    "title":    "My artwork",
    "pin_url":  "https://www.pinterest.com/pin/123456789/",
    "filename": "123456789_a1b2c3d4.jpg",
    "date":     "2025-06-01",
    "tags":     ["illustration", "design"]
  }
]
```

---

## Viewing the gallery

Open `index.html` directly in a browser, or enable **GitHub Pages** on the `main` branch to get a public URL for free.

**GitHub Pages:** Settings → Pages → Branch: `main` / folder: `/ (root)` → Save.  
Your gallery will be live at `https://YOUR_USERNAME.github.io/YOUR_REPO/`.

---

## Customising the schedule

Edit the cron expression in `.github/workflows/sync.yml`:

```yaml
schedule:
  - cron: "0 */6 * * *"   # every 6 hours  ← change this
```

Use <https://crontab.guru> to build a custom schedule.
