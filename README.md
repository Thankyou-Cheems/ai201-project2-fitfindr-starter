# FitFindr

FitFindr is a multi-tool AI agent for secondhand shopping. A user describes an
item they want, the agent searches a mock listing dataset, styles the selected
piece with the user's wardrobe, and creates a short shareable outfit caption.

## Setup With uv

```bash
uv sync --all-groups
```

Create a `.env` file in the repo root:

```bash
GROQ_API_KEY=your_key_here
```

Run tests:

```bash
uv run pytest
```

Run the app:

```bash
uv run python app.py
```

Open the URL Gradio prints in the terminal, usually `http://127.0.0.1:7860`.

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]`

Purpose: searches `data/listings.json` for secondhand items matching the user
request. It filters by max price and size when provided, then scores listings by
keyword overlap across title, description, category, colors, brand, and style
tags.

Output: a ranked list of listing dictionaries. Each dict includes `id`,
`title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`,
`colors`, `brand`, and `platform`. It returns `[]` when no listings match.

### `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

Purpose: uses Groq `llama-3.3-70b-versatile` to suggest one or two complete
outfits for the selected listing. When the wardrobe contains items, the prompt
asks the model to use named wardrobe pieces. When the wardrobe is empty, the
tool asks for general styling advice instead.

Output: a non-empty outfit suggestion string. If the LLM call fails, it returns
a deterministic fallback suggestion.

### `create_fit_card(outfit: str, new_item: dict) -> str`

Purpose: turns the outfit suggestion and selected thrifted item into a short
caption that sounds like a real outfit post.

Output: a 2-4 sentence caption mentioning the item, price, platform, and outfit
vibe. If the outfit string is empty, it returns a descriptive error message
instead of calling the LLM.

## Planning Loop

`run_agent()` uses a step-based planning loop and a shared session dictionary.
It first parses the user query into `description`, `size`, and `max_price`.
Then it sets `next_step = "search"` and enters a loop.

The first tool call is always `search_listings()`. If search returns `[]`, the
agent stores a helpful message in `session["error"]` and returns immediately.
This is the key conditional branch: the agent does not call outfit generation or
fit-card generation without a selected item.

If search returns matches, the agent stores the top result in
`session["selected_item"]` and moves to `suggest_outfit`. The outfit response is
stored in `session["outfit_suggestion"]`, then passed to `create_fit_card`.
After the caption is stored in `session["fit_card"]`, the loop ends and the
completed session is returned.

## State Management

The session dict is the state container for one interaction:

- `query`: original user query.
- `parsed`: extracted `description`, `size`, and `max_price`.
- `search_results`: ranked listings returned by search.
- `selected_item`: the top listing passed into `suggest_outfit`.
- `wardrobe`: the wardrobe selected in the UI.
- `outfit_suggestion`: text returned by `suggest_outfit`.
- `fit_card`: caption returned by `create_fit_card`.
- `error`: early termination message, or `None` on success.
- `steps`: trace of tools called, shown in the UI for demo/debugging.

This lets later tools reuse earlier results without asking the user to re-enter
anything.

## Error Handling

`search_listings`: no matches returns `[]`. The agent then returns an error like
`No listings found for "designer ballgown" with size XXS and under $5. Try
widening the size, raising the budget, or using fewer style keywords.`

`suggest_outfit`: empty wardrobe is not an error. The tool asks the LLM for
general styling advice using categories, colors, and proportions. If Groq is
unavailable, it returns a simple fallback suggestion based on the selected item.

`create_fit_card`: empty outfit input returns `I need a non-empty outfit
suggestion before I can create a fit card.` The tool does not crash and does
not call the LLM for incomplete input.

## Spec Reflection

The spec helped most by making the search branch explicit. Writing down "do not
call `suggest_outfit` when search returns empty" made the planning loop easier
to test and prevented downstream tools from receiving invalid state.

One implementation detail diverged from the original starter suggestion: query
parsing uses regex/string rules instead of an LLM. That keeps the first branch
fast, deterministic, and easy to test. The LLM is reserved for the subjective
styling and caption tasks.

## AI Usage

1. I gave ChatGPT/Codex the Tool 1 section from `planning.md` and asked for a
   deterministic `search_listings()` implementation using `load_listings()`.
   I revised the result to add weighted scoring, tolerant size matching, and
   pytest coverage for empty results and price filtering.

2. I gave ChatGPT/Codex the Planning Loop, State Management, and Architecture
   sections from `planning.md` and asked for `run_agent()`. I kept the
   step-based loop, then added tests that monkeypatch downstream tools to prove
   the no-results branch returns early.

3. I used ChatGPT/Codex to draft Groq prompts for outfit suggestions and fit
   cards. I revised the prompts to be shorter, added deterministic fallbacks,
   and made `create_fit_card()` return a clear message for empty outfit input.
