# Contract: `scripts/compare_vision_models.py` CLI

The team-facing interface for triggering a Comparison Run (FR-001, FR-003).

## Invocation

```bash
python -m scripts.compare_vision_models --models claude-sonnet-5,claude-opus-4-8
```

| Flag | Required | Notes |
|---|---|---|
| `--models` | yes | Comma-separated `model_id`s; each must be a `MODEL_REGISTRY` key. Fewer than 2 is an error (FR-001 requires 2+). |
| `--fixtures-dir` | no | Defaults to `tests/fixtures/food_photos/`; override for a subset/alternate manifest. |

## Behavior

1. Validates every requested `model_id` is registered; unregistered ids fail
   fast before any DB writes or model calls.
2. Creates one `comparison_runs` row (`status='running'`).
3. For each `(model, photo)` pair in the manifest, calls
   `VisionModelClient.analyze` and immediately persists one `model_results`
   row (`ok` or `failed`) — see data-model.md. A failure on one pair never
   stops the remaining pairs (FR-006, Edge Cases).
4. After all pairs are attempted, computes and persists `accuracy_scores`
   for every `(model, metric)` where the manifest has ground truth
   (research.md decision #4), then sets `comparison_runs.status='completed'`.
5. Prints a grouped, human-readable summary to stdout: for each fixture
   photo, every requested model's calorie **and macro ranges** (±20% of the
   stored point value — same method as `meal_logging.format_range_reply`,
   applied to calories and each macro; research.md decision #6) and status
   side by side (FR-002, FR-003), followed by each model's aggregate
   accuracy scores. The summary prints only these numbers and each result's
   status — never a model's `clarifying_question` or any other free text
   (FR-010).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Run completed (individual photo/model failures do not affect this — they're recorded, not fatal) |
| 1 | Run could not start (bad `--models`, missing fixtures, DB unreachable) |

## Non-goals

- Does not accept any flag to change `settings.live_vision_model_id` — live
  model designation is a separate, deliberate config/deploy change
  (research.md decision #1), never a side effect of running a comparison
  (FR-006).
