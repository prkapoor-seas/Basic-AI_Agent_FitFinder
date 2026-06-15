"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Hard filters: price and size
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Score by keyword overlap with description
    keywords = set(description.lower().split())

    def score(listing: dict) -> int:
        searchable = " ".join([
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing["style_tags"]),
            " ".join(listing["colors"]),
            listing.get("brand") or "",
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    scored = [(score(l), l) for l in listings]
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions. If the wardrobe is empty,
        returns general styling advice for the item instead.
    """
    client = _get_groq_client()
    items = wardrobe.get("items", [])

    if not items:
        prompt = (
            f"A thrifter just found this item:\n"
            f"  Name: {new_item['title']}\n"
            f"  Category: {new_item['category']}\n"
            f"  Style tags: {', '.join(new_item['style_tags'])}\n"
            f"  Colors: {', '.join(new_item['colors'])}\n"
            f"  Description: {new_item['description']}\n\n"
            "They don't have a wardrobe on file yet. Give them 1–2 outfit ideas "
            "using this item — describe the types of pieces that would pair well "
            "with it and what overall vibe each outfit creates. Be specific and "
            "conversational, not generic."
        )
    else:
        wardrobe_lines = "\n".join(
            f"  - {it['name']} ({it['category']}, colors: {', '.join(it['colors'])})"
            for it in items
        )
        prompt = (
            f"A thrifter just found this item:\n"
            f"  Name: {new_item['title']}\n"
            f"  Category: {new_item['category']}\n"
            f"  Style tags: {', '.join(new_item['style_tags'])}\n"
            f"  Colors: {', '.join(new_item['colors'])}\n"
            f"  Description: {new_item['description']}\n\n"
            f"Their current wardrobe includes:\n{wardrobe_lines}\n\n"
            "Suggest 1–2 complete outfits using the new item and specific pieces "
            "from their wardrobe. Name each wardrobe piece you use. Be specific "
            "about the vibe and why the combination works."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error string
        rather than raising an exception.
    """
    if not outfit or not outfit.strip():
        return (
            "Could not generate a fit card: outfit description was empty. "
            "Make sure suggest_outfit ran successfully before calling create_fit_card."
        )

    client = _get_groq_client()

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok OOTD caption for this thrifted find.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']:.2f}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- Sound casual and authentic, like a real person posting their outfit — not a product ad\n"
        "- Mention the item name, price, and platform exactly once each, woven naturally into the caption\n"
        "- Capture the specific vibe of the outfit (not just 'cute' or 'stylish')\n"
        "- 2–4 sentences only, no hashtags"
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.2,
    )
    return response.choices[0].message.content.strip()
