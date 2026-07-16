---
name: meal-menu
description: How eating menus are built — TDEE, macro splits, dietary constraints. Use when building or modifying meal plan generation.
---

# Meal menu generation

## Energy math
- BMR: Mifflin-St Jeor. TDEE = BMR × activity factor (1.2–1.725).
- Targets: fat_loss = TDEE −20%; muscle_gain = TDEE +10%; maintenance = TDEE.
- Protein 1.6–2.2 g/kg; fat ≥0.6 g/kg; rest carbs.

## Menu structure
- Generate 1 day at a time (3 meals + 1–2 snacks), each meal: name, ingredients with grams, calories, macros, 2-line prep.
- Respect: allergies (absolute), kosher/halal/vegan flags, disliked foods, budget level, local cuisine (default Israeli/Mediterranean pantry for MVP market).
- Reuse ingredients across the day to keep shopping simple.

## Hard rules
- Never go below 1,200 kcal/day (women) / 1,500 (men) regardless of goal.
- Flag and refuse crash-diet requests; suggest sustainable deficit instead.
- If user shows signs of disordered eating, follow coach-persona escalation rules.
