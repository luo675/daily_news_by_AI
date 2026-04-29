# Seed Maintenance Note

Date: 2026-04-29

This note records seed-maintenance observations only. It does not change code, CLI behavior, or ingestion capability.

Recent maintenance updates:

- Formal baseline rerun was attempted first, as required.
- In the sandbox-restricted environment, every baseline URL failed with `URLError: [WinError 10013]`.
- The failure pattern was uniform across Simon Willison and Anthropic URLs, so this cycle treats that first pass as an environment/network restriction, not as a source-specific or pipeline-specific regression.
- The same baseline URLs were rerun in a network-enabled environment and succeeded 4/4.

Minimal expansion trial:

- Trial candidate: `https://www.oneusefulthing.org/p/what-openai-did`
- Trial mode: single-URL observation rerun with the existing `run_application_batch.py --url ... --no-persist` workflow after the formal baseline was confirmed stable.
- Trial result: workflow passed in a network-enabled environment with 1/1 item succeeded.
- Observation: the candidate remains operationally compatible with the current thin HTML importer and application pipeline.
- Observation: this cycle records operational success only. It does not promote the URL and does not change deferred-candidate status.
- Decision: keep the candidate deferred for now and only reconsider promotion after another explicit maintenance decision.

This cycle's URL-by-URL record:

- `https://simonwillison.net/2024/May/29/training-not-chatting/`: sandbox-restricted run failed with `URLError [WinError 10013]`; network-enabled rerun succeeded.
- `https://simonwillison.net/2024/Dec/31/llms-in-2024/`: sandbox-restricted run failed with `URLError [WinError 10013]`; network-enabled rerun succeeded.
- `https://www.anthropic.com/news/claude-3-5-sonnet`: sandbox-restricted run failed with `URLError [WinError 10013]`; network-enabled rerun succeeded.
- `https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy`: sandbox-restricted run failed with `URLError [WinError 10013]`; network-enabled rerun succeeded.
- `https://www.oneusefulthing.org/p/what-openai-did`: single-URL observation rerun succeeded in the network-enabled environment.
