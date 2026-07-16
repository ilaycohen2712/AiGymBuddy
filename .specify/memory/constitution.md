# AiGymBuddy Constitution
<!-- Example: Spec Constitution, TaskFlow Constitution, etc. -->

## Core Principles

### I. Accuracy honesty
<!-- Example: I. Library-First -->
Calorie estimates are ranges, never false-precision numbers. Every prompt change is regression-tested against labeled fixtures (prompt-tester agent). MAE regression >5% blocks merge.
<!-- Example: Every feature starts as a standalone library; Libraries must be self-contained, independently testable, documented; Clear purpose required - no organizational-only libraries -->

### II. Push, not pull
<!-- Example: II. CLI Interface -->
The bot initiates. Every feature must consider its proactive dimension. Every push message must be answerable to reopen the WhatsApp 24h window. Respect the silence rule — never spam.
<!-- Example: Every library exposes functionality via CLI; Text in/out protocol: stdin/args → stdout, errors → stderr; Support JSON + human-readable formats -->

### III. Safety first
<!-- Example: III. Test-First (NON-NEGOTIABLE) -->
No medical advice, no crash diets (floors: 1200/1500 kcal), disordered-eating escalation per coach-persona skill. Injuries reported by users are absolute constraints.
<!-- Example: TDD mandatory: Tests written → User approved → Tests fail → Then implement; Red-Green-Refactor cycle strictly enforced -->

### IV. Schema discipline
<!-- Example: IV. Integration Testing -->
All LLM outputs validate against versioned JSON schemas before persistence. DB changes only via migrations. Prompts are versioned files in app/prompts/.
<!-- Example: Focus areas requiring integration tests: New library contract tests, Contract changes, Inter-service communication, Shared schemas -->

### V. Platform independence
<!-- Example: V. Observability, VI. Versioning & Breaking Changes, VII. Simplicity -->
All WhatsApp specifics stay in app/whatsapp/. Coaching logic must be channel-agnostic so Telegram or others can be added without rewrites.
<!-- Example: Text I/O ensures debuggability; Structured logging required; Or: MAJOR.MINOR.BUILD format; Or: Start simple, YAGNI principles -->

## Security requirements
<!-- Example: Additional Constraints, Security Requirements, Performance Standards, etc. -->

Webhook signatures verified on every inbound request. Secrets only via environment variables. No PII or health data in logs; phone numbers masked. Subscription status checked before premium features.
<!-- Example: Technology stack requirements, compliance standards, deployment policies, etc. -->

## Development workflow
<!-- Example: Development Workflow, Review Process, Quality Gates, etc. -->

Spec-driven: specify → clarify → plan → tasks → analyze → implement. reviewer agent before merge on sensitive paths; coach-simulator before push-logic releases.
<!-- Example: Code review requirements, testing gates, deployment approval process, etc. -->

## Governance
<!-- Example: Constitution supersedes all other practices; Amendments require documentation, approval, migration plan -->

This constitution supersedes ad-hoc practices. Amendments require updating this file and CLAUDE.md together.
<!-- Example: All PRs/reviews must verify compliance; Complexity must be justified; Use [GUIDANCE_FILE] for runtime development guidance -->

**Version**: 1.0.0 | **Ratified**: 2026-07-16 | **Last Amended**: 2026-07-16
<!-- Example: Version: 2.1.1 | Ratified: 2025-06-13 | Last Amended: 2025-07-16 -->
