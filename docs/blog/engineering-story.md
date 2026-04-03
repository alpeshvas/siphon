# How We Stopped Our LLM From Charging Customers €368.70 For a €67 Cooking Class

We feed data from booking APIs to an LLM. The LLM answers customer questions. That's the product, roughly.

In early 2025, we hooked up our travel assistant to a booking provider called Bokun. Bokun powers a lot of the tours and activities you see on travel marketplaces — cooking classes in Rome, museum passes in Barcelona, that kind of thing. Their API is solid. Their response payloads are not small.

Here's what a single price list call looks like. This is the simplified version:

```json
{
  "activityId": 853863,
  "title": "Pasta Lovers Cooking Class",
  "isPriceConverted": true,
  "conversionRate": 0.62,
  "defaultCurrency": "CAD",
  "pricesByDateRange": [{
    "from": "2026-01-20",
    "to": "2027-01-20",
    "rates": [
      {
        "rateId": 1565415,
        "title": "All Inclusive Package",
        "passengers": [{
          "pricingCategoryId": 789585,
          "title": "Adult",
          "ticketCategory": "ADULT",
          "price": {
            "currency": "EUR", "amount": 184.35,
            "ofWhichTax": 0.0, "converted": true,
            "conversionRate": 0.62, "inferred": true
          },
          "tieredPrices": [], "extras": []
        }],
        "extras": []
      },
      {"rateId": 1760309, "title": "Standard Tour", "passengers": ["..."]},
      {"rateId": 1567944, "title": "Attractions Package", "passengers": ["..."]}
    ]
  }]
}
```

We shoved this into the LLM context. A customer asked: *"How much is the standard cooking class for two adults?"*

The model said €368.70.

The actual price was €67.21 per adult. The model grabbed `184.35` from the All Inclusive Package — different rate, same JSON shape — and doubled it. Confidently. With a smiley face.

## Why This Keeps Happening

We tried the obvious stuff. Prompt engineering: *"Only use the rate titled 'Standard Tour'."* Worked great until a rate was named "Standard Tour: No Add-ons" and the model matched on a partial string. Few-shot examples. Structured output mode. None of it stuck.

The problem wasn't the model. The problem was us. We were dumping 2,000 tokens of nested JSON into the context window when the answer lived in maybe 50 of those tokens. The rest was noise — and worse than noise, because it contained fields with the *exact same names* at different nesting levels. `title` appears on the activity. `title` appears on each rate. `title` appears on each passenger. `amount` repeats everywhere. The model doesn't know which `amount` you mean. It guesses. Sometimes it guesses wrong.

This is just math. More irrelevant context means more opportunities for the model to latch onto the wrong thing. We were basically handing someone a phone book and asking them to find a specific Bob.

## Two Bad Options

We saw two paths forward, and didn't love either.

**Option A: keep dumping raw JSON, keep fixing prompts.** This is whack-a-mole. Every new API shape, every new edge case, another prompt patch. Non-deterministic by nature — the same input can produce different extractions on different runs. Also expensive. We were burning tokens on `ofWhichTax`, `conversionRate`, `tieredPrices`, and `extras` that nobody asked about.

**Option B: write Python extraction functions for every API.** Deterministic, fast, correct. Also a maintenance sinkhole. Every function is the same shape — loops, filters, build a dict — but you write it from scratch every time. When Bokun changes a field name, someone has to go find the right function and update it. Nobody writes tests for these things until they break in production at 2 AM.

What we actually wanted was somewhere in between. Something that could extract the right fields from nested JSON, deterministically, before the LLM ever saw the data. But without writing bespoke code for every endpoint.

So we built a thing.

## Siphon v0.1: Barely a Library

The first version was roughly ten lines of code. It did one thing: follow a dot-notation path through a JSON object.

```yaml
extract:
  id: "$.data.id"
  name: "$.data.name"
  price: "$.data.pricing.amount"
```

We called it Siphon, because it draws the data you need out of a container, like the tube thing. Not our finest naming moment, but it stuck.

Under the hood, there was a single function — `get_by_path` — that split a string on dots and walked through nested dicts. That's it. No arrays, no filtering, no reshaping.

But it worked for the simple cases. And the specs were readable. You could look at a YAML file and immediately know which fields an integration cared about. That was already better than tracing through a Python function.

## v0.2: Arrays

APIs love returning arrays. `get_by_path` couldn't handle them. So we added `[*]`:

```yaml
extract:
  first_item_name: "$.data.items[*].name"
```

One design decision here that we still haven't regretted: `[*]` returns the first match by default. Most of the time you want one value, not a list. "Give me the default address." "Find the primary contact." First match, done. We'd add "give me all of them" later.

The implementation was a recursive function called `extract_all` that split on `[*]`, iterated, and kept going. Multiple `[*]` in one path just meant more recursion. Nothing clever.

## v0.3: Filters and Projection

This is where it got useful. Real extraction isn't "give me the first item." It's "give me the first *active* item, and only its name and ID."

Two new keys: `where` and `select`.

```yaml
extract:
  active_item:
    path: "$.data.items[*]"
    where: {status: "active"}
    select: {item_id: "id", item_name: "name"}
```

`where` was equality matching. `select` was projection — rename fields, flatten nested paths. Both optional, composable. The whole library was still under 100 lines.

This was the version where Siphon went from "cute hack" to something we'd actually use in production.

## v0.4: Collect

There was a gap. Sometimes you want all the active items, not just the first one.

```yaml
all_active:
  path: "$.data.items[*]"
  where: {status: "active"}
  select: {item_id: "id", item_name: "name"}
  collect: true
```

One flag. Same spec, different return type.

We also killed `hoist` in this version. It was a feature we'd added in v0.3 that let you pull parent fields down into child results. It worked, technically. It also made specs harder to read and we kept having to explain what it did. In a library this small, if a feature needs explanation, it doesn't belong. So we deleted it.

## v0.5: The Bokun Breakthrough

Then our friend, the Bokun price list API, broke everything.

The problem: we needed passengers for a specific rate. But `rateId` lives on the rate object, two levels above the passenger. Our `where` clause only looked at the innermost item.

```
pricesByDateRange[*]          ← has "from", "to"
  └─ rates[*]                 ← has "rateId", "title"
       └─ passengers[*]       ← has "pricingCategoryId", "price"
```

We wanted: "give me passengers where rateId is 1760309." But passengers don't have a `rateId` field. Their parent does.

The fix was ancestor filtering. As Siphon walks through nested `[*]` levels, it accumulates properties from each level into a context. The `where` clause checks the whole context, not just the leaf.

```yaml
extract:
  passengers:
    path: "$.pricesByDateRange[*].rates[*].passengers[*]"
    where: {rateId: 1760309}
    select:
      title: "title"
      amount: "price.amount"
    collect: true
```

One line: `where: {rateId: 1760309}`. Siphon figures out that `rateId` is on the rate level. No new keywords. No new syntax. Just smarter matching.

This was the feature that made us feel confident Siphon could handle real APIs, not just the sanitized examples in blog posts.

## v0.6: Chaining

The flat `process()` API hit a ceiling with hierarchical queries. "Find the engineering department, then get its teams, then get members of teams with more than 5 people."

We added `then` for chaining and stole MongoDB's filter operators:

```python
result = query({
    "from": "$.departments[*]",
    "where": {"active": True},
    "select": {"dept": "name"},
    "then": {
        "from": "teams[*]",
        "where": {"size": {"$gte": 5}},
        "select": {"team": "name", "dept": "dept"},
        "sort": [{"field": "name", "order": "asc"}],
        "limit": 10,
        "collect": True
    }
}, data)
```

`$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$exists`, `$regex`, plus `$and`, `$or`, `$not`, `$nor`. The works.

The interesting bit was carry-forward. When a parent level projects fields via `select`, those fields flow down to child levels automatically. Extract "dept" at the top, it shows up next to each team member at the bottom. No manual threading.

## v0.7: Pipelines

Bokun again. Their activity endpoint has rates, start times, and pricing categories as *sibling arrays* — not nested, but linked by foreign key IDs.

```json
{
  "rates": [
    {"id": 1674388, "title": "Express Class", "startTimeIds": [4208239, 4208240]}
  ],
  "startTimes": [
    {"id": 4208239, "externalLabel": "Express Cooking Class", "hour": 14, "minute": 30},
    {"id": 4208240, "externalLabel": "English PM Express", "hour": 18, "minute": 0}
  ]
}
```

You can't nest your way into this. You need to query one array, grab some IDs, then filter a sibling array by those IDs. In SQL, it's a join. In Python, it's a set comprehension and a filter. In Siphon, it became pipelines:

```python
result = pipeline([
    {
        "id": "rate",
        "from": "$.rates[*]",
        "where": {"id": 1674388},
        "select": {"startTimeIds": "startTimeIds"}
    },
    {
        "from": "$.startTimes[*]",
        "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
        "sort": [{"field": "hour", "order": "asc"}],
        "collect": True,
        "select": {"label": "externalLabel", "hour": "hour", "minute": "minute"}
    }
], data)
# [{"label": "Express Cooking Class", "hour": 14, "minute": 30},
#  {"label": "English PM Express", "hour": 18, "minute": 0}]
```

`$stages.rate.startTimeIds` resolves at runtime to the IDs from stage one. Each stage queries the root data independently. The whole pipeline module is under 60 lines.

## Back to the LLM

So. The hallucination.

Here's what the fix actually looked like:

**Before:**
```
Context: {2,000 tokens of raw Bokun JSON}
User: How much for two adults on the standard tour?
LLM: €368.70 ← wrong, grabbed the wrong rate
```

**After:**
```python
clean = process({
    "extract": {
        "passengers": {
            "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
            "where": {"rateId": 1760309},
            "select": {
                "category": "ticketCategory",
                "amount": "price.amount",
                "currency": "price.currency"
            },
            "collect": True
        }
    }
}, raw_response)
```

```
Context: {"passengers": [
  {"category": "ADULT", "amount": 67.21, "currency": "EUR"},
  {"category": "CHILD", "amount": 61.04, "currency": "EUR"}
]}
User: How much for two adults on the standard tour?
LLM: €134.42 (€67.21 per adult) ← correct
```

2,000 tokens became 50. Three similar-looking rates became one unambiguous result. The model stopped guessing because there was nothing left to guess about.

| | Before | After |
|---|---|---|
| Tokens to LLM | ~2,000 | ~50 |
| Irrelevant data | ~95% | 0% |
| Deterministic | No | Yes |
| Cost per query | Baseline | ~97% less |

For AI agents that call multiple tools in a loop, this compounds. Five API calls without extraction: 10,000+ tokens of noise in the context window. Five API calls with Siphon specs: 250 tokens of clean, relevant data. The agent stays focused. The context stays lean. The hallucinations go away.

The spec is the contract between the API and the AI. When the API changes, you update the YAML — not the prompt, not the model, not the application code.

## What We'd Tell You Over Coffee

Build the smallest thing that solves your actual problem. Siphon started as ten lines of path traversal. It's now about 250 lines — still one file, still no dependencies — because we only added things when a real API forced our hand.

Kill features that need explaining. We added `hoist`. We removed `hoist`. The library got better.

Your tests should be real API responses, not made-up JSON. Every major feature in Siphon — ancestor filtering, chaining, pipelines — exists because an actual Bokun endpoint returned something the previous version couldn't handle. Synthetic test data finds bugs. Production data finds missing features.

And if you're feeding API responses to an LLM: don't. Feed it the answer. Let deterministic code do the extraction, and let the model do what models are actually good at — reasoning about clean data, not spelunking through nested JSON.

Siphon is ~250 lines of Python. Zero dependencies. It's at [github.com/alpeshvas/siphon](https://github.com/alpeshvas/siphon). `pip install siphon-dsl`.
