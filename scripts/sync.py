"""
Pinterest Portfolio Sync
Reads a Pinterest board, detects new pins, downloads new images,
and updates works.json.
"""

import os
import json
import time
import hashlib
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone


# ─── Config ───────────────────────────────────────────────────────────────────

PINTEREST_USERNAME  = os.environ.get("PINTEREST_USERNAME", "")
PINTEREST_BOARD     = os.environ.get("PINTEREST_BOARD", "")
PINTEREST_API_TOKEN = os.environ.get("PINTEREST_API_TOKEN", "")

WORKS_JSON  = os.path.join(os.path.dirname(__file__), "..", "works.json")
IMAGES_DIR  = os.path.join(os.path.dirname(__file__), "..", "images")

PINTEREST_API_BASE = "https://api.pinterest.com/v5"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_works() -> list[dict]:
    """Load existing works.json or return an empty list."""
    path = os.path.realpath(WORKS_JSON)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []


def save_works(works: list[dict]) -> None:
    """Save works list to works.json (pretty-printed)."""
    path = os.path.realpath(WORKS_JSON)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(works, f, indent=2, ensure_ascii=False)
    print(f"✔ works.json saved ({len(works)} items)")


def existing_pin_ids(works: list[dict]) -> set[str]:
    """Return the set of pin IDs already in works.json."""
    return {item["pin_id"] for item in works if "pin_id" in item}


def make_filename(pin_id: str, url: str) -> str:
    """
    Derive a safe filename from the pin ID and the original image URL.
    e.g.  123456789_a1b2c3d4.jpg
    """
    ext = ".jpg"
    parsed_path = urllib.parse.urlparse(url).path
    if "." in parsed_path.split("/")[-1]:
        ext = "." + parsed_path.split("/")[-1].rsplit(".", 1)[-1].lower()
        ext = re.sub(r"[^a-z0-9]", "", ext)   # strip query chars
        ext = "." + ext if ext else ".jpg"
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{pin_id}_{url_hash}{ext}"


def download_image(url: str, dest_path: str) -> bool:
    """Download a single image; return True on success."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Pinterest Portfolio Sync)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(dest_path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception as exc:
        print(f"  ✗ Download failed for {url}: {exc}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


# ─── Pinterest API ─────────────────────────────────────────────────────────────

def api_get(endpoint: str, params: dict = None) -> dict:
    """
    Make an authenticated GET request to the Pinterest v5 API.
    Returns the parsed JSON body.
    """
    url = f"{PINTEREST_API_BASE}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {PINTEREST_API_TOKEN}",
            "Content-Type":  "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_board_id(username: str, board_slug: str) -> str | None:
    """
    Search the user's boards to find the one matching `board_slug`.
    The slug is the URL-friendly board name (lowercase, hyphens).
    """
    bookmark = None
    while True:
        params = {"page_size": 100}
        if bookmark:
            params["bookmark"] = bookmark

        data = api_get("boards", params)
        for board in data.get("items", []):
            # board["name"] is human-readable; convert to slug for comparison
            slug = re.sub(r"[^a-z0-9]+", "-", board["name"].lower()).strip("-")
            if slug == board_slug or board["id"] == board_slug:
                return board["id"]

        bookmark = data.get("bookmark")
        if not bookmark:
            break

    return None


def fetch_all_pins(board_id: str) -> list[dict]:
    """
    Fetch every pin on the given board, following pagination.
    Returns a list of raw pin objects from the API.
    """
    pins = []
    bookmark = None

    while True:
        params = {
            "page_size": 100,
            "fields": "id,title,description,link,created_at,media,board_id",
        }
        if bookmark:
            params["bookmark"] = bookmark

        data = api_get(f"boards/{board_id}/pins", params)
        pins.extend(data.get("items", []))

        bookmark = data.get("bookmark")
        if not bookmark:
            break

        # Be polite to the API
        time.sleep(0.3)

    return pins


def best_image_url(pin: dict) -> str | None:
    """
    Extract the highest-quality image URL from a pin object.
    Pinterest v5 nests images inside pin["media"]["images"].
    """
    try:
        images = pin["media"]["images"]
        # Prefer largest available size
        for size in ("originals", "1200x", "736x", "600x", "400x"):
            if size in images:
                return images[size]["url"]
        # Fall back to whatever is first
        if images:
            first = next(iter(images.values()))
            return first.get("url")
    except (KeyError, TypeError):
        pass
    return None


def pin_to_work(pin: dict, filename: str) -> dict:
    """Convert a raw Pinterest pin dict into a works.json entry."""
    created = pin.get("created_at", "")
    # Normalise to ISO date string
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pin_id   = pin.get("id", "")
    title    = (pin.get("title") or pin.get("description") or "Untitled").strip()
    pin_url  = pin.get("link") or f"https://www.pinterest.com/pin/{pin_id}/"
    # Tags: extract hashtags from description if present
    desc     = pin.get("description") or ""
    tags     = re.findall(r"#(\w+)", desc)

    return {
        "pin_id":    pin_id,
        "title":     title,
        "pin_url":   pin_url,
        "filename":  filename,
        "date":      date_str,
        "tags":      tags,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Validate config
    if not PINTEREST_API_TOKEN:
        print("ERROR: PINTEREST_API_TOKEN environment variable is not set.")
        raise SystemExit(1)
    if not PINTEREST_USERNAME:
        print("ERROR: PINTEREST_USERNAME environment variable is not set.")
        raise SystemExit(1)
    if not PINTEREST_BOARD:
        print("ERROR: PINTEREST_BOARD environment variable is not set.")
        raise SystemExit(1)

    # Ensure images directory exists
    os.makedirs(os.path.realpath(IMAGES_DIR), exist_ok=True)

    print(f"▶ Syncing board  : {PINTEREST_USERNAME}/{PINTEREST_BOARD}")

    # 1. Load existing works
    works     = load_works()
    known_ids = existing_pin_ids(works)
    print(f"  Already synced : {len(known_ids)} pin(s)")

    # 2. Resolve board ID
    print("  Resolving board ID …")
    board_id = find_board_id(PINTEREST_USERNAME, PINTEREST_BOARD)
    if not board_id:
        print(f"ERROR: Board '{PINTEREST_BOARD}' not found for user '{PINTEREST_USERNAME}'.")
        raise SystemExit(1)
    print(f"  Board ID       : {board_id}")

    # 3. Fetch all pins
    print("  Fetching pins …")
    all_pins = fetch_all_pins(board_id)
    print(f"  Total pins     : {len(all_pins)}")

    # 4. Filter to new pins only
    new_pins = [p for p in all_pins if p.get("id") not in known_ids]
    print(f"  New pins       : {len(new_pins)}")

    if not new_pins:
        print("✔ Nothing new — exiting.")
        return

    # 5. Download new images and build entries
    added = 0
    for pin in new_pins:
        pin_id    = pin.get("id", "unknown")
        img_url   = best_image_url(pin)

        if not img_url:
            print(f"  ⚠ Skipping pin {pin_id}: no image URL found.")
            continue

        filename  = make_filename(pin_id, img_url)
        dest_path = os.path.join(os.path.realpath(IMAGES_DIR), filename)

        print(f"  ↓ Downloading pin {pin_id} → {filename}")
        if download_image(img_url, dest_path):
            entry = pin_to_work(pin, filename)
            works.append(entry)
            added += 1
        else:
            print(f"  ⚠ Skipping pin {pin_id}: download failed.")

    # 6. Sort newest-first and save
    works.sort(key=lambda w: w.get("date", ""), reverse=True)
    save_works(works)
    print(f"✔ Done — {added} new image(s) added.")


if __name__ == "__main__":
    main()
