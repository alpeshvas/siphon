# Review: iridescent-stirring-flurry (pipeline v0.7)

Design is good. Two implementation fixes needed before coding:

## 1. `resolve_ref`: None vs unknown stage (bug)

In the plan's `resolve_ref`:
```python
output = ctx.get(stage_id)
if output is None:
    raise ValueError(f"Unknown stage: {stage_id}")
```

If a stage with `id="rate"` matches nothing (`collect=False` returns `None`), then `stages_context["rate"] = None`. A downstream `$stages.rate.field` hits `ctx.get("rate")` which returns `None`, raising `ValueError("Unknown stage: rate")` — but the stage exists, it just returned nothing.

**Fix:** `if stage_id not in ctx:` instead of `if output is None:`.

## 2. Typed models: contradictory approach

The plan defines a new `PipelineStageSpec` class but then says "the cleaner approach: add `id` to `ChainSpec`".

**Fix:** Drop `PipelineStageSpec`. Add `id: str | None = None` to `ChainSpec`. `PipelineSpec.stages` becomes `list[ChainSpec]`.
