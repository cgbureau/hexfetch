# HexFetch API

**Extract a ranked colour palette from any URL using pixel-frequency analysis.**

HexFetch takes a screenshot of any webpage and analyses the actual rendered pixels — 
not the CSS stylesheet — to return a ranked colour hierarchy.

---

## Endpoint
GET /palette?url=https://yoursite.com

## Response Structure

```json
{
  "url": "https://stripe.com",
  "primary": {
    "hex": "#635BFF",
    "rgb": { "r": 99, "g": 91, "b": 255 },
    "frequency_pct": 34.2
  },
  "secondary": [
    { "hex": "#F6F9FC", "rgb": { "r": 246, "g": 249, "b": 252 }, "frequency_pct": 18.1 },
    { "hex": "#0A2540", "rgb": { "r": 10, "g": 37, "b": 64 }, "frequency_pct": 11.4 }
  ],
  "tertiary": [...],
  "accent": [...],
  "processing_time_ms": 4821,
  "status": "success"
}
```

## Colour Tiers

| Tier | Count | Description |
|---|---|---|
| Primary | 1 | Most dominant colour on the page |
| Secondary | up to 3 | Next most prominent colours |
| Tertiary | up to 3 | Supporting / background colours |
| Accent | 1–2 | Distinct colours appearing sparingly |

## Notes

- Analysis is **screenshot-based** (pixel-frequency), not CSS parsing
- Returns what the page **visually looks like**, not what's in the stylesheet
- Each colour includes **hex**, **RGB**, and **frequency percentage**
- Processing typically takes 3–8 seconds depending on page weight