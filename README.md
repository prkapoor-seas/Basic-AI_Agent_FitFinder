# FitFindr

A thrift-shopping agent that searches secondhand listings, suggests outfits using your existing wardrobe, and generates a shareable OOTD caption — all from a single natural-language query.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py          # Gradio UI at http://localhost:7860
python agent.py        # CLI smoke test (happy path + no-results path)
pytest tests/          # Full test suite (15 tests)
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Filters and ranks the mock listings dataset against the user's search criteria.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`). Used for relevance scoring. |
| `size` | `str \| None` | Size to filter by, or `None` to skip. Case-insensitive substring match (e.g. `"M"` matches `"S/M"`). |
| `max_price` | `float \| None` | Maximum price inclusive, or `None` to skip price filtering. |

**Output:** `list[dict]` — matching listings sorted by keyword relevance score (highest first). Each dict has fields `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns an empty list if nothing matches.

**How it works:** Loads all listings via `load_listings()`, applies hard filters for price and size, then scores each remaining listing by counting how many description keywords appear in a concatenated string of its title, description, category, tags, colors, and brand. Listings with a score of 0 are dropped.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Uses an LLM to suggest 1–2 complete outfits pairing the thrifted item with pieces the user already owns.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `new_item` | `dict` | A listing dict for the item the user is considering (same structure as a `search_listings` result). |
| `wardrobe` | `dict` | A wardrobe dict with an `items` key containing a list of wardrobe item dicts. May be empty. |

**Output:** `str` — a non-empty string with outfit suggestions. If `wardrobe["items"]` is empty, returns general styling advice for the item type instead of specific combinations.

**Model:** `llama-3.3-70b-versatile` via Groq, `temperature=0.7`.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Generates a casual, shareable 2–4 sentence OOTD caption for the thrifted find.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit`. |
| `new_item` | `dict` | The listing dict for the thrifted item (provides title, price, platform, etc.). |

**Output:** `str` — a caption written in an authentic OOTD voice that mentions the item name, price, and platform once each. If `outfit` is empty or whitespace-only, returns a descriptive error string instead of raising.

**Model:** `llama-3.3-70b-versatile` via Groq, `temperature=1.2` (higher than `suggest_outfit` to ensure caption variation across runs).

---

## Planning Loop

The agent runs a fixed sequential pipeline with one early-exit point. Every step reads from and writes to a single `session` dict.

**Step 1 — Parse the query.**
Calls the LLM at `temperature=0` with the raw user query, asking it to return a JSON object with `description` (str), `size` (str or null), and `max_price` (float or null). If the LLM returns something that can't be parsed as JSON, sets `session["error"]` and returns immediately.

**Step 2 — Search listings.**
Calls `search_listings()` with the three parsed parameters. If the result is an empty list, sets `session["error"]` to a helpful message and returns immediately — `suggest_outfit` and `create_fit_card` are never called.

**Step 3 — Select the top result.**
Sets `session["selected_item"] = session["search_results"][0]` and continues.

**Step 4 — Suggest an outfit.**
Calls `suggest_outfit(new_item, wardrobe)`. This tool never raises — it falls back to general advice when the wardrobe is empty — so no branch is needed. Always continues.

**Step 5 — Create the fit card.**
Calls `create_fit_card(outfit, new_item)`. This tool also never raises — it returns an error string on bad input — so no branch is needed. Always continues.

**Step 6 — Return.**
Returns the completed session dict. `session["error"]` is `None` on a successful run.

---

## State Management

All state lives in a single `session` dict initialized at the start of every run. Tools receive their inputs as explicit function arguments (not the whole dict), which keeps each tool independently testable.

| Field | Written by | Read by |
|---|---|---|
| `query` | caller | LLM parser (step 1) |
| `parsed` | LLM parser | `search_listings` (step 2) |
| `search_results` | `search_listings` | agent (selects top item) |
| `selected_item` | agent | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | caller | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | Gradio UI |
| `error` | agent (on failure) | Gradio UI / caller |

The agent extracts values from the session, passes them explicitly to the tool, and writes the result back — there is no re-prompting or re-deriving of values between steps.

**Verified during testing:** After a successful run, `session["selected_item"] is session["search_results"][0]` evaluated to `True` (same object in memory). The outfit string passed into `create_fit_card` matched `session["outfit_suggestion"]` exactly, confirmed with a mock spy.

---

## Error Handling

### `search_listings` — no results

If the query, size filter, and price ceiling together match no listings, the function returns `[]`. The agent detects this and returns early:

```
session["error"] = "No listings found matching your search. Try a broader description or a higher price limit."
session["fit_card"]  # remains None
session["outfit_suggestion"]  # remains None
```

**Concrete test example:** Query `"designer ballgown size XXS under $5"` returned `[]` from `search_listings`. The agent set the error message and returned without calling `suggest_outfit` — confirmed by patching `suggest_outfit` with `unittest.mock.patch` and asserting `mock_suggest.called == False`.

---

### `suggest_outfit` — empty wardrobe

If `wardrobe["items"]` is an empty list, the tool does not raise. It switches to a different LLM prompt that asks for general styling advice ("what types of pieces pair well with this item, and what vibe does each create") rather than referencing specific owned pieces.

**Concrete test example:** Called `suggest_outfit(graphic_tee, get_empty_wardrobe())` in the test suite. Returned a non-empty string describing Y2K outfit ideas with generic item types (low-rise flared jeans, platform sandals) rather than crashing or returning an empty string. The agent continued to `create_fit_card` without any changes to the planning loop.

---

### `create_fit_card` — empty or missing outfit string

If `outfit` is empty or whitespace-only, the function returns a descriptive error string rather than passing a blank prompt to the LLM:

```python
"Could not generate a fit card: outfit description was empty. Make sure suggest_outfit ran successfully before calling create_fit_card."
```

**Concrete test example:** Called `create_fit_card("", graphic_tee)` and `create_fit_card("   ", graphic_tee)` in the test suite. Both returned the error string. Neither raised an exception. The agent surfaces this string as `session["fit_card"]` so the UI can display it rather than showing a blank panel.

---

## Spec Reflection

**What matched the spec:** The sequential pipeline with a single early-exit after `search_listings` was straightforward to implement. The state management approach — one `session` dict, tools take explicit args, agent writes results back — made it easy to test each tool in isolation before wiring them together. The two-branch prompt logic in `suggest_outfit` (empty vs. populated wardrobe) was the most useful thing to think through in planning because it directly changed what the LLM prompt looked like.

**What I changed from the spec:** The planning.md walkthrough assumed the user's wardrobe context ("baggy jeans and chunky sneakers") would be used to pre-populate the wardrobe dict. In the actual implementation, the wardrobe comes from the data file (`get_example_wardrobe()` or `get_empty_wardrobe()`), not from parsing the query. The query text is only used by `search_listings` via the parsed `description` field. This is a cleaner separation — the UI wardrobe radio button controls which wardrobe is used, and the query controls only the search.

**What I'd change if building this again:** The keyword-overlap scoring in `search_listings` is a bag-of-words count with no weighting — "tee" in the title counts the same as "tee" in the brand field. A weighted scorer (title/tags > description > brand) would produce better ranking. I'd also add a `session["search_results"]` preview to the UI so users can see what else was found and potentially swap to a different listing.

---

## AI Usage

### Instance 1 — Implementing `search_listings`

**What I gave the AI:** The Tool 1 spec from planning.md (parameter names and types, the return value description including all listing dict fields, the failure mode — return empty list not raise), and the note that `load_listings()` from `utils/data_loader.py` handles file I/O.

**What it produced:** A working implementation that loaded listings, applied price and size filters, and scored by keyword overlap. The initial version used `description.split()` for keywords but checked only `listing["title"]` and `listing["description"]` for matches.

**What I changed:** Extended the searchable string to include `category`, `style_tags`, `colors`, and `brand` — otherwise a query like `"streetwear jacket"` would miss listings where `streetwear` appeared only in the `style_tags` list. I also switched the keyword set to lowercase once before the loop rather than inside `score()` for every listing, which avoids repeating the case normalization 40 times per call.

---

### Instance 2 — Implementing `run_agent` (the planning loop)

**What I gave the AI:** The full Mermaid architecture diagram from planning.md, the Planning Loop section (all five numbered steps with explicit branch conditions), and the State Management table showing which field is written by which step. I also included the `_new_session()` dict definition from `agent.py` so it knew the exact field names.

**What it produced:** A correct sequential implementation that matched the spec. However, the generated `_parse_query` helper did not handle the case where the LLM wraps its JSON response in a markdown code fence (` ```json ... ``` `), which Groq's model does intermittently.

**What I changed:** Added a stripping step before `json.loads()` that detects a ` ``` ` prefix and strips the fence and optional `json` language tag before attempting to parse. Without this, the no-results path test would intermittently fail with a JSON parse error rather than the expected "no listings found" message, because the parse error triggers the earlier early-exit with a different error string.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json           # 40 mock secondhand listings
│   └── wardrobe_schema.json    # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py          # load_listings(), get_example_wardrobe(), etc.
├── tests/
│   └── test_tools.py           # 15 pytest tests covering all three tools
├── tools.py                    # search_listings, suggest_outfit, create_fit_card
├── agent.py                    # run_agent() planning loop
├── app.py                      # Gradio UI
├── planning.md                 # Spec, architecture diagram, AI usage plan
├── conftest.py                 # Adds project root to sys.path for pytest
└── requirements.txt
```
