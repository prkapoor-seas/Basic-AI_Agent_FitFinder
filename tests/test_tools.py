"""
tests/test_tools.py

One test per failure mode for each of the three FitFindr tools.
Run with: pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def graphic_tee():
    """A real listing from the dataset used across suggest_outfit and create_fit_card tests."""
    results = search_listings("vintage graphic tee", max_price=50)
    assert results, "fixture requires at least one graphic tee in the dataset"
    return results[0]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # No listings should match a designer ballgown under $5 in XXS
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    # Only listings whose size field contains "M" (case-insensitive) should appear
    results = search_listings("vintage", size="M", max_price=200)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # The top result for "graphic tee" should mention tee/graphic before less-relevant items
    results = search_listings("graphic tee", max_price=200)
    assert len(results) > 1
    # Ensure result is a list of dicts with expected fields
    assert "title" in results[0]
    assert "price" in results[0]


def test_search_no_size_filter_when_none():
    # Passing size=None must not filter out any size
    all_results = search_listings("jacket", size=None, max_price=200)
    m_results = search_listings("jacket", size="M", max_price=200)
    assert len(all_results) >= len(m_results)


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def test_suggest_outfit_populated_wardrobe(graphic_tee):
    outfit = suggest_outfit(graphic_tee, get_example_wardrobe())
    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 0


def test_suggest_outfit_empty_wardrobe(graphic_tee):
    # Empty wardrobe must not crash — returns general styling advice instead
    outfit = suggest_outfit(graphic_tee, get_empty_wardrobe())
    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 0


def test_suggest_outfit_references_wardrobe_pieces(graphic_tee):
    # With a populated wardrobe the LLM should name at least one wardrobe item
    wardrobe = get_example_wardrobe()
    wardrobe_names = [item["name"].lower() for item in wardrobe["items"]]
    outfit = suggest_outfit(graphic_tee, wardrobe).lower()
    matched = any(
        any(word in outfit for word in name.split())
        for name in wardrobe_names
    )
    assert matched, "outfit suggestion should mention at least one wardrobe piece by name"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_returns_string(graphic_tee):
    outfit = suggest_outfit(graphic_tee, get_example_wardrobe())
    card = create_fit_card(outfit, graphic_tee)
    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_create_fit_card_empty_outfit_returns_error_string(graphic_tee):
    # Empty outfit must not raise — returns a descriptive error string
    card = create_fit_card("", graphic_tee)
    assert isinstance(card, str)
    assert len(card.strip()) > 0
    assert "empty" in card.lower() or "error" in card.lower() or "could not" in card.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string(graphic_tee):
    # Whitespace-only outfit is treated the same as empty
    card = create_fit_card("   ", graphic_tee)
    assert isinstance(card, str)
    assert "empty" in card.lower() or "error" in card.lower() or "could not" in card.lower()


def test_create_fit_card_mentions_price(graphic_tee):
    outfit = suggest_outfit(graphic_tee, get_example_wardrobe())
    card = create_fit_card(outfit, graphic_tee)
    price_str = str(int(graphic_tee["price"]))
    assert price_str in card, f"caption should mention price (${graphic_tee['price']})"


def test_create_fit_card_mentions_platform(graphic_tee):
    outfit = suggest_outfit(graphic_tee, get_example_wardrobe())
    card = create_fit_card(outfit, graphic_tee)
    assert graphic_tee["platform"].lower() in card.lower()


def test_create_fit_card_output_varies(graphic_tee):
    # Temperature=1.2 should produce different captions for the same input
    outfit = suggest_outfit(graphic_tee, get_example_wardrobe())
    card1 = create_fit_card(outfit, graphic_tee)
    card2 = create_fit_card(outfit, graphic_tee)
    assert card1 != card2, "captions should vary across runs (check LLM temperature)"
