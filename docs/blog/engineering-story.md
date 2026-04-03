# Siphon: The 100-Line Library That Replaced Thousands of Lines of API Glue Code

*How a weekend frustration turned into a declarative DSL for JSON extraction*

---

## The 2 AM Realization

It started, as many side projects do, with a moment of quiet rage.

Picture this: you're integrating your third external API of the week. The first was a payments provider whose response buried transaction amounts four levels deep inside a `data.transactions[].line_items[].pricing.amount` path. The second was a travel booking API that nested passenger details inside rate tiers inside date ranges — three layers of arrays, each with its own filtering logic. The third was an e-commerce catalog that returned everything about a product except what you actually needed, unless you dug through nested variant arrays and filtered by status.

For each one, the story was the same. You'd write a function. It would loop through the outer array, then the inner array, maybe a third. You'd sprinkle in `if` statements to filter. You'd build a new dictionary to reshape the output. Twenty, thirty, fifty lines of imperative code — just to say "give me the active items' names and prices."

And here's what stung: the *intent* behind each of those functions was trivially simple. "Get the name from `data.id`." "Find all items where status is active." "Rename `pricing.amount` to `cost`." But the *code* to express that intent was verbose, repetitive, and fragile. Change the API response shape, and you'd be rewriting loops all over again.

That night, staring at yet another nested `for` loop inside a `for` loop, a thought crystallized: **What if the extraction logic wasn't code at all? What if it was just... data?**

---

## The Problem, Stated Plainly

Modern applications don't live in isolation. They consume APIs — dozens of them. And every API has its own opinion about how to structure a response. Some nest data under `data.attributes`. Others use flat arrays. Some bury what you need three levels deep. Nearly all of them return far more than you actually want.

The result? Every backend codebase accumulates a quiet layer of **glue code** — functions whose sole job is to reach into a JSON response, pluck out the fields that matter, maybe filter an array, maybe rename a key, and hand back a clean result.

This glue code has a few nasty properties:

1. **It's boilerplate.** The logic is always the same: traverse, filter, project. But you write it from scratch every time.
2. **It's coupled to API shapes.** When a provider changes their response format, your extraction logic breaks — even though what you *wanted* never changed.
3. **It's invisible complexity.** Nobody writes tests for the "just grab the name from the response" function. But when it breaks at 2 AM in production, you notice.
4. **It's not portable.** You can't hand your extraction logic to another team, store it in a config file, or version it alongside an API spec. It's buried in application code.

The question was: could you replace all of this with a simple, declarative spec — a few lines of YAML or JSON — that describes *what* to extract, not *how*?

---

## Starting Small: v0.1 — Just Follow the Path

The first version of Siphon was almost embarrassingly simple. It did exactly one thing: follow a dot-notation path through a JSON object.

```yaml
extract:
  id: "$.data.id"
  name: "$.data.name"
  price: "$.data.pricing.amount"
```

That was it. No arrays. No filtering. No projection. Just: "here's a path, give me the value at the end of it."

Under the hood, the implementation was a single function — `get_by_path` — that split a string on dots and walked through nested dictionaries. Roughly ten lines of Python.

But even this tiny kernel proved something important. Those ten lines replaced dozens of scattered `response["data"]["pricing"]["amount"]` lookups across a codebase. More importantly, the extraction logic was now *data* — you could read it, diff it, store it in a YAML file, and understand at a glance exactly what fields an integration cared about.

The spec was the documentation. The documentation was the spec.

---

## v0.2 — The Array Problem

Simple paths hit a wall the moment an API returns an array. And APIs *love* returning arrays.

Consider a product catalog endpoint that returns:

```json
{
  "data": {
    "id": "prod_123",
    "items": [
      {"id": 1, "name": "Widget"},
      {"id": 2, "name": "Gadget"},
      {"id": 3, "name": "Thing"}
    ]
  }
}
```

You can't use `$.data.items.name` — `items` is a list, not a dict. You need to express "iterate over this array and extract from each element."

Siphon borrowed the `[*]` wildcard syntax from JSONPath:

```yaml
extract:
  first_item_name: "$.data.items[*].name"
```

A small design decision here had lasting consequences: **by default, `[*]` returns only the first match.** This was intentional. In practice, most extraction tasks want a single value — "give me the primary contact" or "find the default address." Returning the first match kept the simple case simple. Getting all matches would come later.

The implementation introduced `extract_all`, a recursive function that splits the path on `[*]`, iterates over the array at that point, and continues traversing the remaining path on each element. It handled multiple `[*]` in a single path naturally — each one just added another level of recursion.

---

## v0.3 — Filtering and Projection: Where Intent Meets Power

Arrays are only half the battle. The real world doesn't just say "give me the first item." It says "give me the first *active* item." Or "give me all items where status is shipped, but only their id and total."

This is where most imperative glue code lives — the `if` statements inside loops, the dictionary comprehensions that build new shapes. v0.3 tackled both with two new spec keys: `where` and `select`.

```yaml
extract:
  active_item:
    path: "$.data.items[*]"
    where: {status: "active"}
    select: {item_id: "id", item_name: "name"}
```

`where` was a simple equality filter — if every key-value pair matched a candidate item, it passed through. `select` was projection — a mapping from desired output field names to source field paths, with dot notation support for reaching into nested objects.

The beauty was in the composition. Each piece — path, where, select — was independently optional. You could filter without projecting. Project without filtering. Or use both together. The spec remained flat and readable, and the implementation stayed under 100 lines.

This was the version where Siphon stopped feeling like a toy and started feeling like a tool.

---

## v0.4 — Collect: The Missing Piece

There was a gap. By default, Siphon returned the first match. But what if you wanted *all* active items? All shipped orders? Every variant of a product?

`collect: true` filled that gap cleanly:

```yaml
extract:
  first_active:
    path: "$.data.items[*]"
    where: {status: "active"}
    select: {item_id: "id", item_name: "name"}

  all_active:
    path: "$.data.items[*]"
    where: {status: "active"}
    select: {item_id: "id", item_name: "name"}
    collect: true
```

Same path. Same filter. Same projection. One returns a single object, the other returns an array. The difference is a single boolean flag.

This version also removed `hoist`, an earlier experiment that added complexity without earning its keep. A lesson in restraint: every feature in a minimal library has to justify its existence, and removing what doesn't work is as important as adding what does.

---

## v0.5 — Ancestor Filtering: The Real-World Breakthrough

Then came the API that broke everything.

A travel booking platform returned pricing data in a three-level hierarchy: date ranges contained rates, rates contained passengers. To extract passengers for a specific rate, you needed to filter by `rateId` — but `rateId` lived on the *rate* object, not on the passenger.

```json
{
  "pricesByDateRange": [
    {
      "from": "2026-01-20",
      "rates": [
        {
          "rateId": 1760309,
          "passengers": [
            {"title": "Adult", "price": {"amount": 67.21}},
            {"title": "Child", "price": {"amount": 61.04}}
          ]
        }
      ]
    }
  ]
}
```

In imperative code, this is a triple-nested loop with a condition on the middle level. In the existing Siphon, it was impossible — `where` only saw the innermost item.

The solution was **ancestor filtering**: as Siphon traverses nested arrays, it accumulates properties from each level into a context object. The `where` clause checks against this merged context, not just the leaf item.

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

One line in the `where` clause. No triple-nested loop. No intermediate variables. Just: "I want passengers where the rate ID is this value" — and Siphon figures out which level `rateId` lives at.

This was a turning point. It solved a class of problems that previously required custom code for every API — hierarchical filtering across parent-child relationships in nested JSON. And it did it without adding a single new spec key.

---

## v0.6 — The Chaining Engine: MongoDB Meets JSONPath

The flat `process()` API was clean, but it had a ceiling. Some queries needed multi-level extraction: "find the departments, then for each department find the teams, then for each team find the members." Each level might have its own filters, its own projections, its own sort order.

v0.6 introduced the **chaining query engine** with a `then` keyword for hierarchical extraction and a full set of MongoDB-style filter operators:

```python
from siphon import query

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

The operator set — `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$exists`, `$regex` — plus logical combinators `$and`, `$or`, `$not`, `$nor` — gave Siphon the expressiveness of a query language while keeping the declarative spec format.

A critical design choice: **field carry-forward**. When a parent level uses `select`, those projected fields automatically flow into child levels. This meant you could extract a department's name at the outer level and have it appear alongside each team member at the inner level — without manually threading data through.

The implementation decomposed multi-`[*]` paths into nested chain specs automatically. A path like `$.a[*].b[*].c[*]` became a three-level chain, each level handling one array traversal. This kept the user-facing API simple while the engine handled the complexity internally.

---

## v0.7 — Pipelines: When Queries Need to Talk to Each Other

The final evolution (so far) addressed a subtle but common problem: **cross-referencing between sibling arrays.**

Imagine an API that returns products in one array and inventory in another. You want all products that are in stock — but "in stock" is determined by the inventory array, not the product array. In SQL, this is a join. In imperative code, it's building a lookup set from one array and filtering the other.

Siphon's **pipeline API** solved this with named stages that can reference each other:

```python
from siphon import pipeline

result = pipeline([
    {
        "id": "in_stock",
        "from": "$.inventory[*]",
        "where": {"quantity": {"$gt": 0}},
        "select": {"sku": "sku"},
        "collect": True
    },
    {
        "from": "$.products[*]",
        "where": {"sku": {"$in": "$stages.in_stock.sku"}},
        "select": {"name": "name", "sku": "sku"},
        "collect": True
    }
], data)
```

The `$stages.in_stock.sku` reference resolves at runtime to the list of SKUs from the first stage. It's GitHub Actions-style composition: each stage runs independently against the root data, but can reference prior stages' outputs in its `where` clause.

The implementation is elegant in its simplicity. A `resolve_refs` function recursively walks the `where` dict, replacing `$stages.<id>.<field>` strings with actual values from completed stages. Each stage then delegates to the existing `query()` engine. The entire pipeline module is under 60 lines.

---

## In Production: The Bokun Integration

Every library has a story about the integration that proved it wasn't just a side project anymore. For Siphon, that was Bokun.

Bokun is a travel activities and booking platform. If you've ever booked a cooking class in Rome, a snorkeling tour in Bali, or a museum pass in Barcelona through an online marketplace, there's a good chance Bokun's API was involved somewhere in the chain. Its API is comprehensive — and comprehensively nested.

Consider what happens when a travel marketplace needs to display available time slots for a cooking class. The Bokun activity endpoint returns a structure like this:

```json
{
  "id": 853863,
  "title": "Pasta Lovers Cooking Class",
  "defaultRateId": 1674388,
  "rates": [
    {
      "id": 1674388,
      "title": "English - Express Afternoon Cooking Class",
      "startTimeIds": [4208239, 4208240],
      "pricingCategoryIds": [120729, 120731, 120732]
    },
    {
      "id": 1641235,
      "title": "Extended Cooking Class + Grocery Market Tour",
      "startTimeIds": [2937449],
      "pricingCategoryIds": [120729, 120731, 120732]
    }
  ],
  "startTimes": [
    {"id": 2937449, "externalLabel": "Cooking Class + Market", "hour": 9, "minute": 0},
    {"id": 4208239, "externalLabel": "Express Cooking Class", "hour": 14, "minute": 30},
    {"id": 4208240, "externalLabel": "English PM Express Class", "hour": 18, "minute": 0}
  ],
  "pricingCategories": [
    {"id": 120729, "title": "Adult", "ticketCategory": "ADULT"},
    {"id": 120731, "title": "Child", "ticketCategory": "CHILD"},
    {"id": 120732, "title": "Infant", "ticketCategory": "INFANT"}
  ]
}
```

Notice the shape. Rates, start times, and pricing categories live in **sibling arrays** linked by foreign key IDs — `startTimeIds` and `pricingCategoryIds`. To show the user "for the Express Afternoon class, available times are 2:30 PM and 6:00 PM, for Adults, Children, and Infants" — you need to:

1. Find the rate by ID
2. Extract its `startTimeIds`
3. Filter the `startTimes` array to only those IDs
4. Do the same for `pricingCategoryIds` against `pricingCategories`

In imperative code, that's a lookup table, two filter loops, and a handful of intermediate variables. Every time the shape changes or a new field is needed, someone edits a Python function and hopes the tests still pass.

With Siphon's pipeline API, the entire extraction is a data structure:

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

# [
#   {"label": "Express Cooking Class", "hour": 14, "minute": 30},
#   {"label": "English PM Express Class", "hour": 18, "minute": 0}
# ]
```

Two stages. The first finds the rate and captures its start time IDs. The second filters the start times array using those IDs — a cross-reference join expressed as a `$stages` reference. No intermediate variables. No loops. The spec reads like a description of the business logic: "find this rate, then find its start times, sorted by hour."

The pricing side of Bokun pushed things further. The price list endpoint nests data three levels deep — date ranges contain rates, rates contain passengers (ticket types), and each passenger has currency-converted pricing:

```python
spec = {
    "extract": {
        "passengers": {
            "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
            "where": {"rateId": 1760309},
            "select": {
                "title": "title",
                "ticketCategory": "ticketCategory",
                "amount": "price.amount",
                "currency": "price.currency"
            },
            "collect": True
        }
    }
}
```

That `where: {rateId: 1760309}` is ancestor filtering in action — `rateId` lives on the rate object two levels above the passenger, but Siphon's context accumulation finds it automatically.

### What the Integration Taught Us

The Bokun integration wasn't just a user of Siphon — it was the proving ground that shaped the library's evolution:

- **Ancestor filtering (v0.5)** was born because the price list API required filtering passengers by their parent rate's ID — a pattern that's impossible with leaf-only matching.
- **The chaining engine (v0.6)** was built because rates, start times, and pricing categories live in sibling arrays that need to be joined — a fundamentally different pattern from nested traversal.
- **The pipeline API (v0.7)** emerged because real integrations need to cross-reference multiple independent arrays in sequence, not just drill into one hierarchy.

Each version of Siphon was shaped by a real API response that the previous version couldn't handle cleanly. The Bokun integration was the pressure that forged the library's most powerful features — and validated that a declarative spec could replace hundreds of lines of bespoke extraction code in a production system handling real bookings, real money, and real travelers.

---

## The Architecture of Restraint

Looking at Siphon today — v0.7, the full library — what's remarkable is what it *isn't*.

It isn't a query language. It doesn't parse SQL or implement a custom grammar. It isn't a transformation framework. It doesn't reshape data into arbitrary structures. It isn't a schema validator. It doesn't care what your data looks like beyond basic dict-and-list traversal.

What it is: roughly 250 lines of Python, zero runtime dependencies, and a spec format that fits on an index card.

```
path:     Where to look         "$.data.items[*].name"
where:    What to keep          {status: "active"}
select:   What to call it       {item_id: "id"}
collect:  One or many?          true / false
then:     Go deeper             {from: "...", ...}
```

This restraint isn't accidental. Every proposed feature during development was measured against a simple question: **"Can the user solve this by composing existing primitives, or does this genuinely require new capability?"**

`hoist` was added and removed. Nested `select` was considered and rejected. Custom aggregation functions were proposed and declined. Each time, the answer was either "compose what exists" or "this makes the spec too hard to read at a glance."

The result is a library where the spec *is* the documentation. You can hand a Siphon YAML file to someone who has never seen the library, and they can read it. They know what data is being extracted, what's being filtered, and what the output shape looks like. No code to trace. No functions to follow. Just data describing data.

---

## What We Learned

Building Siphon reinforced a few principles that apply well beyond this library:

**1. Declarative beats imperative for stable patterns.**
If you find yourself writing the same shape of code over and over — loops, filters, projections — that's a DSL waiting to be born. The pattern is the language; you just need to name its parts.

**2. Start with the spec, not the implementation.**
Every version of Siphon started by writing example specs — what *should* this look like? — and then building the engine to support them. This kept the API user-friendly because the user-facing format was always the starting point.

**3. Features removed are as valuable as features added.**
Removing `hoist` in v0.4 made the library better. Not because `hoist` was broken, but because its presence made specs harder to reason about. In a minimal library, cognitive overhead is the real cost of a feature.

**4. Real APIs are the best test suite.**
Every major Siphon feature — ancestor filtering, chaining, pipelines — was born from a real API that the existing version couldn't handle cleanly. Synthetic test cases find bugs; real use cases find missing capabilities.

**5. 100 lines is a feature, not a limitation.**
When your library is small enough to read in one sitting, users trust it. They can debug it. They can fork it, understand it, and extend it. The entire core of Siphon fits in a single file. That's not a constraint to apologize for — it's a design goal to protect.

---

## Where Siphon Is Today

Siphon is open source, published on PyPI as `siphon-dsl`, and used in production for API integrations that range from e-commerce catalogs to travel booking platforms. It supports three APIs:

- **`process(spec, data)`** — The original flat extraction API
- **`query(spec, data)`** — The chaining query engine with MongoDB-style filters
- **`pipeline(stages, data)`** — Multi-stage extraction with cross-references

It has optional Pydantic integration for typed specs, optional `requests` integration for direct API fetching, and a test suite that covers everything from simple path extraction to multi-level ancestor filtering with logical operators.

And it's still about 250 lines of Python with zero runtime dependencies.

Sometimes the best tool for the job is the smallest one that works.

---

*Siphon is available at [github.com/alpeshvas/siphon](https://github.com/alpeshvas/siphon). Install with `pip install siphon-dsl`.*
