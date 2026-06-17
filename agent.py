"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────


def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,  # original user query
        "parsed": {},  # extracted description / size / max_price
        "search_results": [],  # list of matching listing dicts
        "selected_item": None,  # top result, passed into suggest_outfit
        "wardrobe": wardrobe,  # user's wardrobe dict
        "outfit_suggestion": None,  # string returned by suggest_outfit
        "fit_card": None,  # string returned by create_fit_card
        "error": None,  # set if the interaction ended early
        "steps": [],  # planning trace for debugging/demo
    }


# ── query parsing ────────────────────────────────────────────────────────────

PRICE_PATTERNS = [
    re.compile(
        r"\b(?:under|below|less than|up to|maximum|max|budget of)\s*\$?(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(r"\$(\d+(?:\.\d+)?)\s*(?:or less|max|maximum)?", re.IGNORECASE),
]

SIZE_PATTERN = re.compile(
    r"\b(?:in\s+)?(?:size|sz)\s*[:#-]?\s*"
    r"(US\s*\d+(?:\.\d+)?|W\d{2}(?:\s*L\d{2})?|"
    r"XXS|XXL|XL|XS|S/M|M/L|L/XL|XS/S|S|M|L|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

WARDROBE_CUES = re.compile(
    r"\b(i mostly wear|i usually wear|my wardrobe|my closet|i wear|with my)\b",
    re.IGNORECASE,
)

FILLER_PATTERN = re.compile(
    r"\b(i am|i'm|im|looking for|look for|find me|show me|"
    r"what'?s out there|how would i style it|please|want|need|a pair of)\b",
    re.IGNORECASE,
)


def _extract_price(query: str) -> float | None:
    """Extract a max price from the query if one is present."""
    for pattern in PRICE_PATTERNS:
        match = pattern.search(query)
        if match:
            return float(match.group(1))
    return None


def _extract_size(query: str) -> str | None:
    """Extract a size from explicit size language."""
    match = SIZE_PATTERN.search(query)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1).upper()).strip()


def _extract_description(query: str) -> str:
    """Remove constraints and wardrobe context to get the search description."""
    search_part = WARDROBE_CUES.split(query, maxsplit=1)[0]
    for pattern in PRICE_PATTERNS:
        search_part = pattern.sub(" ", search_part)
    search_part = SIZE_PATTERN.sub(" ", search_part)
    search_part = FILLER_PATTERN.sub(" ", search_part)
    search_part = re.sub(r"\b(?:under|below|less than|up to)\b", " ", search_part)
    search_part = re.sub(r"[$,.:;!?()]", " ", search_part)
    search_part = re.sub(r"\s+", " ", search_part).strip()
    search_part = re.sub(r"^(?:a|an|the|some)\s+", "", search_part, flags=re.IGNORECASE)
    return search_part or query.strip()


def _parse_query(query: str) -> dict:
    """Parse the user query into tool-ready search parameters."""
    return {
        "description": _extract_description(query),
        "size": _extract_size(query),
        "max_price": _extract_price(query),
    }


def _format_search_error(parsed: dict) -> str:
    """Build a helpful no-results error message."""
    filters = []
    if parsed.get("size"):
        filters.append(f"size {parsed['size']}")
    if parsed.get("max_price") is not None:
        filters.append(f"under ${parsed['max_price']:.0f}")
    filter_text = f" with filters: {', '.join(filters)}" if filters else ""
    return (
        f'No listings found for "{parsed["description"]}"{filter_text}. '
        "Try widening the size, raising the budget, or using fewer style keywords."
    )


# ── planning loop ─────────────────────────────────────────────────────────────


def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    if not query or not query.strip():
        session["error"] = "Enter what kind of secondhand item you want to find."
        return session

    session["parsed"] = _parse_query(query)
    next_step = "search"

    while next_step:
        if next_step == "search":
            parsed = session["parsed"]
            session["search_results"] = search_listings(
                parsed["description"],
                size=parsed["size"],
                max_price=parsed["max_price"],
            )
            session["steps"].append("search_listings")

            if not session["search_results"]:
                session["error"] = _format_search_error(parsed)
                next_step = None
                continue

            session["selected_item"] = session["search_results"][0]
            next_step = "suggest_outfit"

        elif next_step == "suggest_outfit":
            session["outfit_suggestion"] = suggest_outfit(
                session["selected_item"],
                session["wardrobe"],
            )
            session["steps"].append("suggest_outfit")
            if not session["outfit_suggestion"]:
                session["error"] = "I found a listing, but could not build an outfit."
                next_step = None
                continue
            next_step = "create_fit_card"

        elif next_step == "create_fit_card":
            session["fit_card"] = create_fit_card(
                session["outfit_suggestion"],
                session["selected_item"],
            )
            session["steps"].append("create_fit_card")
            next_step = None

        else:
            session["error"] = f"Unknown planning step: {next_step}"
            next_step = None

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
