# AiGymBuddy — WhatsApp AI Personal Trainer

A WhatsApp bot that replaces a personal trainer: builds workout plans, builds eating menus, and tracks calories from food photos — proactively (push, not pull).

## Development process — Spec-Driven (Spec Kit)
Every feature goes through this agentic flow. Do not skip steps:
1. `/speckit.constitution` — (once) project principles, already seeded in .specify/memory/constitution.md
2. `/speckit.specify <feature description>` — WHAT & WHY → spec.md on a new feature branch
3. `/speckit.clarify` — resolve open questions in the spec
4. `/speckit.plan` — HOW: architecture & tech choices → plan.md
5. `/speckit.tasks` — chop plan into small agent-sized tasks → tasks.md
6. `/speckit.analyze` — consistency check across spec/plan/tasks
7. `/speckit.implement` — execute tasks; use the reviewer agent before merging

## Custom agents (.claude/agents/)
- **prompt-tester** — run after ANY change to prompts or the vision pipeline
- **reviewer** — run before merging webhook/data/billing changes
- **coach-simulator** — run before releasing push-rule or conversation changes

## Domain knowledge (.claude/skills/)
whatsapp-api · calorie-estimation · workout-planning · meal-menu · coach-persona · db-schema
Always follow these when touching their domains.

## Stack
Python 3.11+ / FastAPI · Postgres (Supabase) · Claude API (vision + chat) · Meta WhatsApp Business Cloud API · Stripe · deployed on Railway/Render.

## Iron rules
- Prompts are versioned files in app/prompts/ — never inline strings.
- LLM outputs are schema-validated before DB insert.
- Calorie results shown to users as ranges, never exact numbers.
- No medical advice; safety escalation per coach-persona skill.
- Every proactive message must be answerable (keeps the 24h window open).
