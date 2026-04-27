# Seed Maintenance Note

Date: 2026-04-21

This note records seed-maintenance observations only. It does not change code, CLI behavior, or ingestion capability.

Recent maintenance updates:

- `https://openai.com/index/hello-gpt-4o/` is no longer classified as a known failure.
- The URL was removed from `known_failures.txt` after a successful run in a network-enabled environment.
- The URL is not promoted to a formal seed yet. Promotion is deferred until a later maintenance trial confirms it is stable enough to track.

Minimal expansion trial:

- Trial candidate: `https://www.oneusefulthing.org/p/what-openai-did`
- Trial mode: reuse the existing `run_application_batch.py --url-list ... --no-persist` workflow with the current four baseline URLs plus this one candidate.
- Trial result: workflow passed in a network-enabled environment with 5/5 items succeeded.
- Observation: the candidate is operationally compatible with the current thin HTML importer and application pipeline.
- Observation: structured output was usable for trial review, including opportunities, risks, open questions, and related topic signals.
- Observation: extraction quality is not fully clean yet; at least one noisy entity (`But`) appeared in the candidate result, so this trial should not be treated as an automatic promotion signal.
- Decision: keep the candidate deferred for now and only reconsider promotion after another explicit maintenance decision.
