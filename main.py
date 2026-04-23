import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import time

from extractor import extract_palette

app = FastAPI(
    title="HexFetch",
    description="Extract a ranked colour palette from any webpage using pixel-frequency analysis. Returns primary, secondary, tertiary and accent colours as hex and RGB values.",
    version="1.0.0",
    contact={
        "name": "HexFetch API",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class ColourValue(BaseModel):
    hex: str
    rgb: dict
    frequency_pct: float


class PaletteResponse(BaseModel):
    url: str
    primary: Optional[ColourValue]
    secondary: list
    tertiary: list
    accent: list
    processing_time_ms: int
    status: str


@app.get("/")
def root():
    return {
        "name": "HexFetch",
        "version": "1.0.0",
        "description": "Extract ranked colour palettes from any URL using pixel-frequency analysis.",
        "docs": "/docs",
        "endpoint": "/palette?url=https://example.com"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/palette", response_model=PaletteResponse)
async def get_palette(
    url: str = Query(..., description="The full URL to analyse (must include https://)")
):
    """
    **Extract a ranked colour palette from any webpage.**

    Pass any public URL and receive back:
    - **Primary** colour (most dominant)
    - **Secondary** colours (up to 3)
    - **Tertiary** colours (up to 3)  
    - **Accent** colours (1–2 sparingly used distinct colours)

    Each colour is returned as both **hex** and **RGB** values,
    with a **frequency percentage** showing how much of the page it covers.

    Analysis is screenshot-based (pixel-frequency), not CSS parsing —
    so you get what the page actually *looks* like visually.
    """

    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    start = time.time()

    try:
        palette = await extract_palette(url)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyse URL. Ensure it is publicly accessible. Error: {str(e)}"
        )

    elapsed = int((time.time() - start) * 1000)

    return {
        "url": url,
        "primary": palette["primary"],
        "secondary": palette["secondary"],
        "tertiary": palette["tertiary"],
        "accent": palette["accent"],
        "processing_time_ms": elapsed,
        "status": "success"
    }