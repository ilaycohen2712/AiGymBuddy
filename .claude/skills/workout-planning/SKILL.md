---
name: workout-planning
description: How workout plans are structured and generated. Use when building or modifying plan generation, progression logic, or plan schemas.
---

# Workout plan generation

## Inputs (from user profile)
goal (fat_loss | muscle_gain | general_fitness), experience (beginner | intermediate | advanced), days_per_week (2–6), equipment (gym | home_basic | bodyweight), injuries/limits (free text — respect absolutely).

## Plan structure (JSON schema in app/pipelines/workout_plan.py)
- Split by days_per_week: 2–3 → full body; 4 → upper/lower; 5–6 → push/pull/legs.
- Each day: 4–7 exercises, sets×reps, rest seconds, RPE target, 1-line form cue.
- Beginners: machines + compound basics, RPE ≤7, no advanced techniques.

## Progression rules
- Week-over-week: +2.5–5% load OR +1–2 reps, never both.
- Deload every 4–6 weeks (60% volume).
- If user reports a missed week → repeat, don't progress.

## Safety limits
- Never prescribe: max-effort 1RM tests, exercises conflicting with a reported injury, >6 training days/week.
- Never give medical advice; pain reports → "stop and see a professional."
