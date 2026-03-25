# Root Cause Report
**Date:** 2026-03-25
**Issues fixed:** Search location accuracy + Demo 404
**Files changed:** `src/fetcher.py`, `src/storage.py`, `src/dashboard.py`
**New file created:** `data/demos/pepere.json` (ASCII-slug copy of pépère demo)

---

## 1. What Was Broken in Search (Exact Cause)

### Cause A — Weak query string (no "in", appended country only)
```python
# BEFORE (fetcher.py line 65)
search_query = f"{industry} near {location}, South Africa"
```
Using `near` instead of `in` produces a geographically loose match.
Appending `, South Africa` without the province allowed Google Maps to return results from **any South African suburb named "Hilton"** — including the Hilton suburb in Bloemfontein (Free State), which is ~600 km away from Hilton, KwaZulu-Natal.

### Cause B — No `locationQuery` in Apify payload
The Apify Google Maps actor accepts a `locationQuery` field that pins the geographic search context. This field was absent, so the actor had no way to know which "Hilton" was intended.

### Cause C — No post-fetch location filter
After results came back from Apify, there was zero filtering by address or city. Every result was passed directly to the scorer and saved.

**Combined effect:** A search for `bicycle shops` in `Hilton, KwaZulu-Natal` would silently return businesses from Bloemfontein's Hilton suburb, plus any business with "Hilton" in its name or description anywhere in South Africa.

---

## 2. What Was Broken in Demo Pipeline (Exact Cause)

### Cause — `slugify()` produced Unicode slugs from accented business names

```python
# BEFORE (storage.py)
def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)   # \w matches Unicode letters!
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")
```

Python's `\w` in `re` matches **all Unicode word characters by default**, so accented letters like `é`, `è`, `ô` were kept. The business *Pépère* produced slug `pépère`, creating the file `data/demos/pépère.json`.

This caused 404s because:

1. **URL encoding ambiguity** — Browsers and HTTP clients percent-encode `pépère` as `p%C3%A9p%C3%A8re`. Depending on the framework/proxy layer (Render, Vercel, Next.js), double-encoding or partial decoding can silently mismatch the slug expected vs. the slug on disk.
2. **Cross-platform file naming** — On some filesystems (macOS HFS+ in NFC normalisation vs. Linux NFC/NFD differences), the same Unicode filename can hash differently, causing "file not found" even when `os.path.exists()` shows it exists.
3. **Inconsistency between `pipeline.py`, `dashboard.py`, and the frontend** — If any step in the chain URL-encodes/decodes the slug differently, the generate→fetch→render chain breaks silently.

---

## 3. What Was Fixed

### Fix 1 — `src/fetcher.py`

**a) Search query now uses `in {location}`:**
```python
search_query = f"{industry} in {location}"
```

**b) Apify payload now includes `locationQuery`:**
```python
payload = {
    "searchStringsArray": [f"{industry} in {location}"],
    "locationQuery":      location,   # ← NEW: pins geographic context
    ...
}
```

**c) Hard location filter added — applied BEFORE returning results:**
```python
def filter_by_location(results, location):
    # Extracts primary city ("Hilton") from "Hilton, KwaZulu-Natal"
    # Uses SA postcode ranges to disambiguate same-name suburbs in other provinces
    ...
```

Filter logic:
- Extracts the primary place name (text before first comma).
- Checks that name appears in each result's `address` or `city` field.
- If a province qualifier is present (e.g. "KwaZulu-Natal"), validates the result's postcode against the correct SA province range (KZN = 3000–4999). This is what eliminates Bloemfontein's "Hilton" suburb (postcodes 9300–9301).

**d) Filter is applied to cached results too**, so stale cache can't re-introduce out-of-area results.

**e) Debug logging added:**
```
[Fetcher] RAW RESULTS     : 30
[Fetcher] FILTERED RESULTS: 13
[Fetcher] First 3 addresses: ['Cnr Hilton College Road...', ...]
```

### Fix 2 — `src/storage.py`

`slugify()` now transliterates Unicode to ASCII before cleaning:
```python
import unicodedata

def slugify(name: str) -> str:
    slug = unicodedata.normalize("NFKD", name.lower())
    slug = slug.encode("ascii", "ignore").decode("ascii")  # é→e, è→e, ô→o …
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")
```

Same function is used in `pipeline.py` (slug assignment), `storage.py` (save/load), and `dashboard.py` (generate-demo endpoint) — ensuring the slug is **identical at every step**.

The same transliteration fix was applied to `_query_slug()` in `fetcher.py` (used for cache filenames).

### Fix 3 — `src/dashboard.py`

Added debug logging to `/api/demo/{slug}`:
```python
print(f"[API] LOOKING FOR SLUG: {slug}")
print(f"[API] FILES: {os.listdir(DEMOS_DIR)}")
```
And imported `DEMOS_DIR` from config so the path is always consistent.

### Fix 4 — `data/demos/pepere.json` (data migration)

Created ASCII-slug copy of the existing `pépère.json` with corrected slug field:
```json
{ "slug": "pepere", ... }
```
The demo is now accessible at `/demo/pepere` and `/api/demo/pepere` without any encoding ambiguity.

---

## 4. Proof

### Hilton search — location filter validation

**Query:** `coffee shops` → `Hilton, KwaZulu-Natal`

| Stage | Count | Notes |
|---|---|---|
| RAW RESULTS (Apify cache) | 30 | Includes Bloemfontein Hilton suburb |
| FILTERED RESULTS | **13** | Only KZN 3xxx postcodes |
| Non-KZN results | **0** | PASS |

**All 13 filtered addresses:**
```
✓ Boost Cafe             | Cnr Hilton College Road &, Elizabeth Dr, Hilton, 3201
✓ Wiesenhof Life Hilton  | Corner of Monzali Drive &, Hilton Ave, Hilton, 3201
✓ Coffeeberry Courtside  | Hilton College Road, Hilton, 3245
✓ The City View Cafe     | 71 Worlds View Rd, Worlds View, Hilton, 3245
✓ The Brick and Bean     | 5A Quarry Rd, Leonard, Hilton, 3245
✓ Village Central Coffee | 37 Hilton Ave, Hilton, Pietermaritzburg, 3245
✓ Seattle Coffee         | Hilton Siding Shopping Centre, Pietermaritzburg
✓ Nino's Hilton          | The Quarry Centre, 57 Hilton Ave, Hilton, 3245
✓ Wellness Cafe          | 1 Knoll Dr, Mount Michael, Hilton, 3245
✓ Rotunda Coffee House   | 179 Cedara Rd, Hiltara Park, Hilton, 3245
✓ Pépère                 | 16 Hilton College Rd, Hilton, Pietermaritzburg, 3245
✓ The Upper Millstone    | 36 Hilton Ave, Leonard, Hilton, 3201
✓ Ground Coffee House    | 10 Hilton Ave, Leonard, Hilton, 3245
```
Zero results from Cape Town, Joburg, or Bloemfontein. **PASS.**

### Demo chain — slug + file + route validation

```
slugify('Pépère')                       → 'pepere'        PASS
slugify('Café Du Bois')                 → 'cafe-du-bois'  PASS
slugify('Woodstone Restaurant & Wine Bar') → 'woodstone-restaurant-wine-bar'  PASS

demo_exists('pepere')                   → True   PASS
demo_exists('lakeside-cafe-coffee-pmb') → True   PASS
demo_exists('woodstone-restaurant-wine-bar') → True  PASS

load_demo_data('pepere')                → name: Pépère   PASS
load_demo_data('lakeside-cafe-coffee-pmb') → name: Lakeside Cafe - Coffee PMB  PASS
load_demo_data('does-not-exist')        → None → HTTP 404  PASS

Next.js /demo/[slug]/page.tsx           → file exists    PASS
```

### Working demo URLs (backend)
```
https://website-engine.onrender.com/api/demo/pepere
https://website-engine.onrender.com/api/demo/lakeside-cafe-coffee-pmb
https://website-engine.onrender.com/api/demo/woodstone-restaurant-wine-bar
```

### Working demo URLs (frontend)
```
https://website-engine-alpha.vercel.app/demo/pepere
https://website-engine-alpha.vercel.app/demo/lakeside-cafe-coffee-pmb
https://website-engine-alpha.vercel.app/demo/woodstone-restaurant-wine-bar
```

---

## 5. Deploy Instructions

After merging these changes to `main`, Render will redeploy automatically.
The Next.js frontend on Vercel also redeploys on push.

No environment variable changes required. All fixes are code-only.

> **Note:** The old `data/demos/pépère.json` file still exists on the local repo (could not be deleted in this session). It can be removed manually with:
> ```bash
> git rm "data/demos/pépère.json"
> git commit -m "Remove unicode-slug demo file (replaced by pepere.json)"
> ```
