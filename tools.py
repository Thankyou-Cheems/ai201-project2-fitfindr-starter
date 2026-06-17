"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL_NAME = "llama-3.3-70b-versatile"
STOP_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "for",
    "i",
    "im",
    "in",
    "is",
    "it",
    "looking",
    "me",
    "of",
    "or",
    "the",
    "to",
    "under",
    "with",
}


# ── Groq client ───────────────────────────────────────────────────────────────


def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _chat_completion(prompt: str, *, temperature: float, max_tokens: int) -> str:
    """Call Groq and return the assistant message content."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are FitFindr, a concise secondhand fashion styling "
                    "assistant. Be specific, natural, and useful."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _tokenize(text: str) -> list[str]:
    """Normalize text into searchable lowercase tokens."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())
        if token not in STOP_WORDS
    ]


def _item_search_text(listing: dict) -> dict[str, str]:
    """Prepare searchable text fields for a listing."""
    style_tags = " ".join(listing.get("style_tags") or [])
    colors = " ".join(listing.get("colors") or [])
    brand = listing.get("brand") or ""
    return {
        "title": listing.get("title", ""),
        "description": listing.get("description", ""),
        "category": listing.get("category", ""),
        "style_tags": style_tags,
        "colors": colors,
        "brand": brand,
        "all": " ".join(
            [
                listing.get("title", ""),
                listing.get("description", ""),
                listing.get("category", ""),
                style_tags,
                colors,
                brand,
                listing.get("platform", ""),
            ]
        ),
    }


def _size_matches(listing_size: str, requested_size: str | None) -> bool:
    """Return whether a listing size satisfies the optional requested size."""
    if not requested_size:
        return True

    listing_normalized = listing_size.upper().replace(" ", "")
    requested_normalized = requested_size.upper().replace(" ", "")
    if listing_normalized == requested_normalized:
        return True
    if requested_normalized in listing_normalized.split("/"):
        return True

    listing_tokens = set(re.findall(r"[A-Z]+|\d+(?:\.\d+)?", listing_size.upper()))
    requested_tokens = re.findall(r"[A-Z]+|\d+(?:\.\d+)?", requested_size.upper())
    if not requested_tokens:
        return True

    if requested_normalized.startswith("US"):
        return all(token in listing_tokens for token in requested_tokens)
    if requested_normalized.startswith("W"):
        return requested_normalized in listing_normalized
    if requested_normalized in {"XS", "S", "M", "L", "XL", "XXL"}:
        return requested_normalized in listing_tokens
    if requested_normalized.isnumeric():
        return requested_normalized in listing_tokens

    return requested_normalized in listing_normalized


def _score_listing(description: str, listing: dict) -> int:
    """Score a listing by weighted keyword overlap."""
    fields = _item_search_text(listing)
    query = description.lower().strip()
    tokens = _tokenize(description)
    if not tokens:
        return 0

    score = 0
    all_text = fields["all"].lower()
    if query and query in all_text:
        score += 8

    style_tags = fields["style_tags"].lower()
    for tag in listing.get("style_tags") or []:
        tag_lower = tag.lower()
        if tag_lower in query or query in tag_lower:
            score += 5

    for token in tokens:
        if re.search(rf"\b{re.escape(token)}\b", fields["title"].lower()):
            score += 4
        if re.search(rf"\b{re.escape(token)}\b", style_tags):
            score += 3
        if re.search(
            rf"\b{re.escape(token)}\b",
            f"{fields['category']} {fields['colors']} {fields['brand']}".lower(),
        ):
            score += 2
        if re.search(rf"\b{re.escape(token)}\b", fields["description"].lower()):
            score += 1

    return score


def _format_item_for_prompt(item: dict) -> str:
    """Render a listing dict for an LLM prompt."""
    return (
        f"{item.get('title', 'Unknown item')} | "
        f"category: {item.get('category', 'unknown')} | "
        f"size: {item.get('size', 'unknown')} | "
        f"condition: {item.get('condition', 'unknown')} | "
        f"price: ${float(item.get('price', 0)):.2f} | "
        f"colors: {', '.join(item.get('colors') or []) or 'unknown'} | "
        f"style tags: {', '.join(item.get('style_tags') or []) or 'unknown'} | "
        f"platform: {item.get('platform', 'unknown')}"
    )


def _fallback_outfit(new_item: dict, wardrobe: dict) -> str:
    """Return deterministic styling advice if the LLM is unavailable."""
    title = new_item.get("title", "this thrifted piece")
    colors = ", ".join(new_item.get("colors") or ["neutral"])
    tags = ", ".join(new_item.get("style_tags") or ["casual"])
    wardrobe_items = (wardrobe or {}).get("items") or []
    if wardrobe_items:
        names = [item.get("name", "wardrobe staple") for item in wardrobe_items[:3]]
        return (
            f"Style {title} with {names[0]} and {names[1]} for a {tags} look. "
            f"Finish it with {names[2]} so the {colors} tones feel intentional."
        )
    return (
        f"Style {title} with relaxed denim, a clean base layer, and simple shoes. "
        f"The {colors} palette and {tags} tags would work best with pieces that "
        "balance the item instead of competing with it."
    )


def _fallback_fit_card(outfit: str, new_item: dict) -> str:
    """Return a deterministic caption if the LLM is unavailable."""
    title = new_item.get("title", "this thrifted find")
    platform = new_item.get("platform", "a secondhand shop")
    price = float(new_item.get("price", 0))
    return (
        f"Found {title} on {platform} for ${price:.0f} and built the whole look "
        f"around it. {outfit.strip()[:180]}"
    )


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

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    scored_results: list[tuple[int, float, dict]] = []

    for listing in listings:
        if max_price is not None and float(listing.get("price", 0)) > max_price:
            continue
        if not _size_matches(str(listing.get("size", "")), size):
            continue

        score = _score_listing(description, listing)
        if score > 0:
            scored_results.append((score, float(listing.get("price", 0)), listing))

    scored_results.sort(key=lambda result: (-result[0], result[1]))
    return [listing for _, _, listing in scored_results]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────


def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    if not new_item:
        return "I need a selected listing before I can suggest an outfit."

    wardrobe_items = (wardrobe or {}).get("items") or []
    item_text = _format_item_for_prompt(new_item)

    if wardrobe_items:
        wardrobe_text = "\n".join(
            (
                f"- {item.get('name', 'Unnamed item')} "
                f"({item.get('category', 'unknown')}; "
                f"colors: {', '.join(item.get('colors') or []) or 'unknown'}; "
                f"style tags: {', '.join(item.get('style_tags') or []) or 'unknown'}; "
                f"notes: {item.get('notes') or 'none'})"
            )
            for item in wardrobe_items
        )
        prompt = f"""
Suggest 1-2 complete outfits using this thrifted item and the user's wardrobe.
Use named wardrobe pieces when they fit. Keep the answer to 4-6 sentences.
Mention why the pieces work together and include one practical styling detail.

Thrifted item:
{item_text}

User wardrobe:
{wardrobe_text}
""".strip()
    else:
        prompt = f"""
The user has not entered any wardrobe items yet. Give general styling advice
for this thrifted item. Name the types of pieces, colors, and proportions that
would pair well. Keep the answer to 3-5 sentences.

Thrifted item:
{item_text}
""".strip()

    try:
        response = _chat_completion(prompt, temperature=0.7, max_tokens=360)
    except Exception:
        return _fallback_outfit(new_item, wardrobe or {})

    return response or _fallback_outfit(new_item, wardrobe or {})


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────


def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return "I need a non-empty outfit suggestion before I can create a fit card."
    if not new_item:
        return "I need a selected listing before I can create a fit card."

    item_text = _format_item_for_prompt(new_item)
    prompt = f"""
Create a short shareable outfit caption for this thrifted find.

Rules:
- 2-4 sentences.
- Sound casual and specific, like a real outfit post.
- Mention the item title, price, and platform naturally once.
- Do not sound like a product listing.
- No hashtags.

Thrifted item:
{item_text}

Outfit suggestion:
{outfit}
""".strip()

    try:
        response = _chat_completion(prompt, temperature=0.95, max_tokens=220)
    except Exception:
        return _fallback_fit_card(outfit, new_item)

    return response or _fallback_fit_card(outfit, new_item)
