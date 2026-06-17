import agent
import tools
from agent import run_agent
from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)

    assert isinstance(results, list)
    assert len(results) > 0
    assert (
        "tee" in results[0]["title"].lower()
        or "tee" in " ".join(results[0]["style_tags"]).lower()
    )


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)

    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)

    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("90s track jacket", size="M", max_price=None)

    assert results
    assert results[0]["id"] == "lst_004"


def test_suggest_outfit_empty_wardrobe(monkeypatch):
    listing = search_listings("vintage graphic tee", size=None, max_price=50)[0]

    def fake_chat_completion(prompt, *, temperature, max_tokens):
        assert "has not entered any wardrobe items" in prompt
        return "Pair it with relaxed denim, clean sneakers, and a simple jacket."

    monkeypatch.setattr(tools, "_chat_completion", fake_chat_completion)
    result = suggest_outfit(listing, get_empty_wardrobe())

    assert "relaxed denim" in result


def test_create_fit_card_empty_outfit():
    listing = search_listings("vintage graphic tee", size=None, max_price=50)[0]

    result = create_fit_card("", listing)

    assert "non-empty outfit suggestion" in result


def test_create_fit_card_uses_listing_context(monkeypatch):
    listing = search_listings("vintage graphic tee", size=None, max_price=50)[0]

    def fake_chat_completion(prompt, *, temperature, max_tokens):
        assert listing["title"] in prompt
        assert str(int(listing["price"])) in prompt
        assert listing["platform"] in prompt
        return "Found the tee for a steal and styled it with worn-in denim."

    monkeypatch.setattr(tools, "_chat_completion", fake_chat_completion)
    result = create_fit_card("Wear it with baggy jeans.", listing)

    assert "styled it" in result


def test_agent_no_results_returns_early(monkeypatch):
    def fake_search(description, size=None, max_price=None):
        return []

    def should_not_run(*args, **kwargs):
        raise AssertionError("Downstream tools should not run after empty search.")

    monkeypatch.setattr(agent, "search_listings", fake_search)
    monkeypatch.setattr(agent, "suggest_outfit", should_not_run)
    monkeypatch.setattr(agent, "create_fit_card", should_not_run)

    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())

    assert session["error"]
    assert session["fit_card"] is None
    assert session["steps"] == ["search_listings"]


def test_agent_happy_path_state_flow(monkeypatch):
    listing = {
        "id": "lst_test",
        "title": "Test Graphic Tee",
        "description": "A test tee",
        "category": "tops",
        "style_tags": ["graphic tee"],
        "size": "M",
        "condition": "good",
        "price": 20.0,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    }

    def fake_search(description, size=None, max_price=None):
        assert description == "vintage graphic tee"
        assert max_price == 30.0
        return [listing]

    def fake_suggest(new_item, wardrobe):
        assert new_item is listing
        assert wardrobe["items"]
        return "Wear it with baggy jeans and chunky sneakers."

    def fake_card(outfit, new_item):
        assert outfit == "Wear it with baggy jeans and chunky sneakers."
        assert new_item is listing
        return "Thrifted tee, easy fit."

    monkeypatch.setattr(agent, "search_listings", fake_search)
    monkeypatch.setattr(agent, "suggest_outfit", fake_suggest)
    monkeypatch.setattr(agent, "create_fit_card", fake_card)

    session = run_agent(
        "I'm looking for a vintage graphic tee under $30.",
        get_example_wardrobe(),
    )

    assert session["error"] is None
    assert session["selected_item"] is listing
    assert (
        session["outfit_suggestion"] == "Wear it with baggy jeans and chunky sneakers."
    )
    assert session["fit_card"] == "Thrifted tee, easy fit."
    assert session["steps"] == [
        "search_listings",
        "suggest_outfit",
        "create_fit_card",
    ]
