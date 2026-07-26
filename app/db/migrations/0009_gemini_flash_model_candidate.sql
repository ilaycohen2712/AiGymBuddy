-- Gemini Flash model migration (specs/006-gemini-flash-migration).
-- app/services/vision_models.py's MODEL_REGISTRY gained a "gemini-flash-latest"
-- entry, now the default live model (app/config.py::live_vision_model_id).
-- meals.model_id and model_results.model_id are FK'd to model_candidates(id)
-- (0003_vision_model_comparison.sql), so every registry key needs a matching
-- row here or a live meal insert violates that foreign key.

INSERT INTO model_candidates (id, display_name) VALUES
    ('gemini-flash-latest', 'Gemini Flash');
