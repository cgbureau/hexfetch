import io
import re
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright
from sklearn.cluster import KMeans
from typing import List, Tuple, Optional


# ── Colour Utilities ───────────────────────────────────────────────────────────

def hex_to_rgb(hex_str: str) -> Optional[Tuple]:
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    if len(hex_str) != 6:
        return None
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rgb_to_hex(r, g, b) -> str:
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def colour_entry(rgb: tuple, pixel_freq: float = 0.0) -> dict:
    """pixel_freq is always a true 0.0-1.0 pixel frequency value."""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return {
        "hex": rgb_to_hex(r, g, b),
        "rgb": {"r": r, "g": g, "b": b},
        "frequency_pct": round(pixel_freq * 100, 1)
    }


def get_saturation(rgb: tuple) -> float:
    r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
    cmax, cmin = max(r, g, b), min(r, g, b)
    if cmax == 0:
        return 0.0
    return (cmax - cmin) / cmax


def get_brightness(rgb: tuple) -> float:
    return max(rgb[0], rgb[1], rgb[2]) / 255


def is_neutral(rgb: tuple) -> bool:
    """
    Kills whites, near-whites, pure blacks, and unsaturated greys.
    Preserves dark colours with chromatic character (navy, dark green).
    Preserves bright saturated colours (neon green, coral, orange).
    """
    sat = get_saturation(rgb)
    brightness = get_brightness(rgb)

    if brightness > 0.90 and sat < 0.15:
        return True
    if brightness < 0.10 and sat < 0.15:
        return True
    if sat < 0.09:
        return True

    return False


def colour_distance(c1: tuple, c2: tuple) -> float:
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def find_pixel_match(rgb: tuple, pixel_colours: list) -> Tuple[float, bool]:
    """
    Returns (frequency, found) for the nearest pixel cluster.
    frequency is the true pixel frequency (0.0-1.0).
    found is True if any cluster is within distance 45.
    """
    best_freq = 0.0
    found = False
    for px_rgb, px_freq in pixel_colours:
        if colour_distance(rgb, px_rgb) < 45:
            found = True
            if px_freq > best_freq:
                best_freq = px_freq
    return best_freq, found


# ── CSS Extraction by Zone ─────────────────────────────────────────────────────

async def extract_header_colours(page) -> List[Tuple]:
    """
    Header zone — highest trust.
    Logo, nav, primary CTA all live here.
    Only captures elements in the top 200px.
    """
    raw = await page.evaluate("""
        () => {
            const colours = [];
            const headerSelectors = [
                'header', 'nav', '[class*="header"]', '[class*="navbar"]',
                '[class*="nav-bar"]', '[class*="topbar"]', '[class*="top-bar"]',
                '[role="banner"]', '[role="navigation"]'
            ];
            for (const sel of headerSelectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.top > 200) return;
                    const s = window.getComputedStyle(el);
                    colours.push(s.backgroundColor);
                    colours.push(s.color);
                    colours.push(s.borderBottomColor);
                    el.querySelectorAll('*').forEach(child => {
                        const cs = window.getComputedStyle(child);
                        colours.push(cs.backgroundColor);
                        colours.push(cs.color);
                        const tag = child.tagName.toLowerCase();
                        if (tag === 'a' || tag === 'button' ||
                            child.className.toString().includes('btn')) {
                            colours.push(cs.backgroundColor);
                            colours.push(cs.color);
                            colours.push(cs.borderColor);
                        }
                    });
                });
            }
            return colours;
        }
    """)
    return _parse_colour_values(raw)


async def extract_cta_colours(page) -> List[Tuple]:
    """
    Button and CTA colours across the full page.
    Action brand colours — high intentionality.
    Skips transparent backgrounds.
    """
    raw = await page.evaluate("""
        () => {
            const colours = [];
            const selectors = [
                'button', '[class*="btn"]', '[class*="button"]',
                '[class*="cta"]', 'a[class*="primary"]',
                'a[class*="action"]', '[type="submit"]'
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (s.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                        s.backgroundColor !== 'transparent') {
                        colours.push(s.backgroundColor);
                    }
                    colours.push(s.color);
                    colours.push(s.borderColor);
                });
            }
            return colours;
        }
    """)
    return _parse_colour_values(raw)


async def extract_body_colours(page) -> List[Tuple]:
    """
    Full stylesheet sweep. Lower trust — catches supporting colours
    but also catches hidden states. Pixel gatekeeper filters these.
    """
    raw = await page.evaluate("""
        () => {
            const colours = new Set();
            for (const sheet of Array.from(document.styleSheets)) {
                try {
                    for (const rule of Array.from(sheet.cssRules || [])) {
                        if (rule.style) {
                            const props = [
                                'color', 'background-color', 'border-color',
                                'fill', 'stroke', 'outline-color',
                                'text-decoration-color'
                            ];
                            for (const prop of props) {
                                const val = rule.style.getPropertyValue(prop);
                                if (val) colours.add(val);
                            }
                        }
                    }
                } catch(e) {}
            }
            return Array.from(colours);
        }
    """)
    return _parse_colour_values(list(raw))


def _parse_colour_values(raw: list) -> List[Tuple]:
    rgb_pattern = re.compile(r'rgba?\((\d+),\s*(\d+),\s*(\d+)')
    hex_pattern = re.compile(r'#([0-9a-fA-F]{3,6})\b')
    results = []
    for value in raw:
        if not value:
            continue
        m = rgb_pattern.search(str(value))
        if m:
            results.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
            continue
        m = hex_pattern.search(str(value))
        if m:
            rgb = hex_to_rgb(m.group(1))
            if rgb:
                results.append(rgb)
    return results


# ── Pixel Extraction ───────────────────────────────────────────────────────────

def extract_pixel_colours(image_bytes: bytes, n_clusters=24) -> List[Tuple]:
    """
    KMeans pixel clustering. Returns (rgb, true_frequency) pairs.
    true_frequency is always 0.0-1.0 representing share of pixels.
    Used as: visibility gatekeeper + fallback for image-based colours.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((800, 800))
    pixels = np.array(image).reshape(-1, 3).astype(float)

    sample_size = min(10000, len(pixels))
    indices = np.random.choice(len(pixels), sample_size, replace=False)
    sample = pixels[indices]

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(sample)

    centres = kmeans.cluster_centers_.astype(int)
    counts = np.bincount(kmeans.labels_)
    total = counts.sum()

    sorted_idx = np.argsort(counts)[::-1]
    return [(tuple(centres[i]), float(counts[i]) / total) for i in sorted_idx]


# ── Scoring & Ranking ──────────────────────────────────────────────────────────

def score_and_rank(
    header_colours: list,
    cta_colours: list,
    body_colours: list,
    pixel_colours: list
) -> list:
    """
    Two-stage pipeline:

    Stage 1 — CSS colours validated by pixels:
      Header colours: base score 1.0 (highest trust)
      CTA colours:    base score 0.8
      Body colours:   base score 0.3 (lowest trust, most noise)
      All must be visible in pixels to qualify.
      Score = base + (saturation * 0.4) + (pixel_freq * 0.3)

    Stage 2 — Pixel-only fallback:
      Catches image-based brand colours CSS completely missed (e.g. Monzo coral).
      Only qualifies if: saturation >= 0.30 AND pixel_freq >= 0.01
      These thresholds are intentionally low to catch prominent image colours.

    Final: deduplicate at distance 50, rank by score.
    Pixel frequency stored separately for clean display.
    """

    # scored[rgb] = (score, pixel_freq)
    scored = {}

    def add_colour(rgb, base_score):
        if is_neutral(rgb):
            return
        pixel_freq, visible = find_pixel_match(rgb, pixel_colours)
        if not visible:
            return
        sat = get_saturation(rgb)
        score = base_score + (sat * 0.4) + (pixel_freq * 0.3)
        if rgb not in scored or scored[rgb][0] < score:
            scored[rgb] = (score, pixel_freq)

    for rgb in header_colours:
        add_colour(rgb, 1.0)

    for rgb in cta_colours:
        add_colour(rgb, 0.8)

    for rgb in body_colours:
        add_colour(rgb, 0.3)

    # Stage 2: pixel-only fallback for image-based brand colours
    for px_rgb, px_freq in pixel_colours:
        if is_neutral(px_rgb):
            continue
        sat = get_saturation(px_rgb)
        # Intentionally permissive — catches coral, gradient colours etc.
        if sat < 0.30 or px_freq < 0.01:
            continue
        already_covered = any(
            colour_distance(px_rgb, c) < 45 for c in scored
        )
        if not already_covered:
            pixel_score = (sat * 0.5) + (px_freq * 0.5)
            scored[px_rgb] = (pixel_score, px_freq)

    # Sort by score descending
    ranked = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)

    # Deduplicate
    final = []
    seen = []
    for rgb, (score, pixel_freq) in ranked:
        if all(colour_distance(rgb, s) >= 50 for s in seen):
            final.append((rgb, pixel_freq))
            seen.append(rgb)

    return final


# ── Main Entry Point ───────────────────────────────────────────────────────────

async def extract_palette(url: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        header_colours = await extract_header_colours(page)
        cta_colours = await extract_cta_colours(page)
        body_colours = await extract_body_colours(page)
        screenshot = await page.screenshot(full_page=False, type="png")
        await browser.close()

    pixel_colours = extract_pixel_colours(screenshot)

    ranked = score_and_rank(
        header_colours,
        cta_colours,
        body_colours,
        pixel_colours
    )

    result = {"primary": None, "secondary": [], "tertiary": [], "accent": []}

    for i, (colour, pixel_freq) in enumerate(ranked):
        entry = colour_entry(colour, pixel_freq)
        if i == 0:
            result["primary"] = entry
        elif i <= 3:
            result["secondary"].append(entry)
        elif i <= 6:
            result["tertiary"].append(entry)
        elif i <= 8:
            result["accent"].append(entry)
        if i >= 8:
            break

    return result