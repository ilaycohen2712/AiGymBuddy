# Phase 1 Data Model: Text-Based Meal Logging

## `meals` table (extended)

Migration `0008_text_meal_logging.sql`:

```sql
ALTER TABLE meals ALTER COLUMN photo_media_id DROP NOT NULL;
ALTER TABLE meals ADD COLUMN text_entries text[] NOT NULL DEFAULT '{}';
```

| Column | Type | Notes |
|---|---|---|
| `photo_media_id` | `text`, nullable (was `NOT NULL`) | The *first* contribution's photo media ID — `NULL` when the meal was started by a text description instead of a photo. Existing photo-originated meals are unaffected (column already populated). |
| `photo_media_ids` | `text[]` | Unchanged. Every photo contribution's media ID, in order. Empty array for a meal with no photo contributions at all. |
| `text_entries` | `text[]` NEW | Every text-description contribution's raw body, in order, parallel to `photo_media_ids`. Empty array for a meal with no text contributions. |
| `foods`, `total_calories`, `confidence`, `model_id` | unchanged | Combined/accumulated identically regardless of whether a contribution came from a photo or text — the estimation *result* has the same shape either way (see below), so combination logic in `append_to_meal` doesn't need to know which source produced it. |

**Invariant**: a meal always has at least one contribution — `len(photo_media_ids) + len(text_entries) >= 1` always holds, same as `len(photo_media_ids) >= 1` held before this change (a meal is never created with zero contributions).

**Derived "how many contributions" signal** (replaces the current `len(meal.photo_media_ids) > 1` check in `meal_logging._reply_for_logged_meal`):

```python
def _contribution_count(meal: MealRecord) -> int:
    return len(meal.photo_media_ids) + len(meal.text_entries)
```

A meal with `_contribution_count(meal) > 1` gets the "item added + running total" reply shape; a meal with exactly 1 gets the single-shot full-breakdown reply shape — unchanged logic, just no longer assuming every contribution was a photo.

## `MealRecord` (Python dataclass, `app/db/queries.py`)

```python
@dataclass
class MealRecord:
    id: str
    user_id: str
    logged_at: dt.datetime
    photo_media_ids: list[str] = field(default_factory=list)
    text_entries: list[str] = field(default_factory=list)   # NEW
    foods: list[dict] = field(default_factory=list)
    total_calories: float = 0.0
    confidence: float | None = None
    model_id: str | None = None
```

## `MealRepository` protocol (extended)

`create_meal` and `append_to_meal` gain a way to record a text contribution instead of a photo one. Rather than two parallel method pairs (`create_meal`/`create_text_meal`, `append_to_meal`/`append_text_to_meal`), both existing methods take an optional origin marker so callers share one code path:

```python
async def create_meal(
    self,
    user_id: str,
    foods: list[dict],
    total_calories: float,
    confidence: float | None,
    now: dt.datetime,
    model_id: str | None = None,
    media_id: str | None = None,     # NEW — was required `media_id: str`
    text_entry: str | None = None,   # NEW — exactly one of media_id/text_entry is set
) -> MealRecord: ...

async def append_to_meal(
    self,
    meal: MealRecord,
    foods: list[dict],
    total_calories: float,
    confidence: float | None,
    model_id: str | None = None,
    media_id: str | None = None,     # NEW
    text_entry: str | None = None,   # NEW
) -> MealRecord: ...
```

Callers pass exactly one of `media_id` / `text_entry` — never both, never neither (enforced by the two call sites: `meal_logging.py` always passes `media_id`, `text_meal_logging.py` always passes `text_entry`). `log_meal_photo` in `meal_logging.py` is generalized into a shared `log_meal_contribution` helper both `meal_logging.py` and `text_meal_logging.py` call, so the grouping-window and daily-totals-accumulation logic (`app/services/meal_logging.py` lines ~19-89 today) is not duplicated.

## Text meal description (ephemeral — ranked estimation result, not a DB entity)

The output of the new `calorie_text.md` prompt, same shape as the vision pipeline's result (`app/services/vision.py`'s return shape):

```json
{
  "foods": [
    {"name": "", "portion_grams": 0, "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
  ],
  "total_calories": 0,
  "confidence": 0.0,
  "clarifying_question": null,
  "is_food_description": true
}
```

One addition versus the vision schema: **`is_food_description: bool`** — `true` when the text was a food-logging attempt (whether or not the estimate is complete), `false` when the text isn't about logging food at all (a question, small talk, anything else). This is the single field `text_meal_logging.py` checks to decide whether to return a reply or `None` (defer to the next dispatch layer) — distinct from `foods` being empty, since `foods` is legitimately empty while `clarifying_question` is set (a food-logging attempt with a materially missing quantity, FR-012), which is a different case from "not food-logging at all" (empty `foods`, `clarifying_question: null`, `is_food_description: false`).
