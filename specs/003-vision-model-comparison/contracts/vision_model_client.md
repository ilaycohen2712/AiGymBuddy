# Contract: `VisionModelClient` Protocol

This project has no external HTTP surface for this feature (it's an internal
research tool); the contract that matters is the internal interface every
candidate model must implement, since it's what the live path and the
comparison path both call, unchanged.

Defined in `app/services/vision_models.py`.

```python
class VisionModelClient(Protocol):
    async def analyze(
        self,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
        clarification: str | None = None,
    ) -> dict: ...
```

## Preconditions
- `image_bytes` is a non-empty image payload already validated by the
  WhatsApp media-download path (`app/whatsapp/media.py`) — this contract does
  not re-validate image content.

## Postconditions
- On success, returns a dict conforming to the existing calorie-estimation
  schema (`.claude/skills/calorie-estimation/SKILL.md`):
  ```json
  {"foods":[{"name":"","portion_grams":0,"calories":0,"protein_g":0,"carbs_g":0,"fat_g":0}],
   "total_calories":0,"confidence":0.0,"clarifying_question":null}
  ```
- On a non-conforming or unparseable model response, raises `ValueError` or
  `json.JSONDecodeError` — mirrors `app/services/vision.py`'s existing
  `_extract_json_block` / `_validate_schema` behavior today. Callers (both
  the live path and the comparison orchestrator) are responsible for
  catching these and recording the failure; the client itself never returns
  a partial or best-effort dict.

## Registry

```python
MODEL_REGISTRY: dict[str, VisionModelClient]
```

- Keys are stable `model_id` strings (e.g. `"claude-sonnet-5"`) that must
  match a row in the `model_candidates` table (data-model.md).
- `app/services/vision.py`'s `analyze_photo()` resolves
  `MODEL_REGISTRY[settings.live_vision_model_id]` and delegates to it —
  its own public signature and behavior are unchanged from today.
- `app/services/vision_comparison.py` iterates an explicit list of
  `model_id`s (given by the caller/CLI), resolving each the same way — it
  never implicitly includes or excludes the live model.

## Compatibility

- Every existing caller of `app/services/vision.py::analyze_photo` keeps
  working with zero changes — this is a refactor of `vision.py`'s internals,
  not a change to its public contract.
