# Baseline Seed Status

Date: 2026-04-29

This note records the current baseline seed set for the next maintenance cycle. It is a seed-maintenance update only, not a code change.

Current retained formal seed URLs:

- `https://simonwillison.net/2024/May/29/training-not-chatting/`
- `https://simonwillison.net/2024/Dec/31/llms-in-2024/`
- `https://www.anthropic.com/news/claude-3-5-sonnet`
- `https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy`

Deferred candidates that remain deferred:

- `https://www.oneusefulthing.org/p/what-openai-did`
- `https://www.anthropic.com/news/a-new-initiative-for-developing-third-party-model-evaluations/`

Maintenance status:

- The latest maintenance rerun on 2026-04-29 first failed in the sandbox-restricted environment with `URLError: [WinError 10013]`, which is consistent with a local network permission restriction rather than an application regression.
- The formal seed baseline was then rerun in a network-enabled environment with the existing `run_application_batch.py --url-list ... --no-persist` workflow.
- The current formal seed baseline reran successfully with 4/4 items succeeded.

Formal seed baseline result details:

- `https://simonwillison.net/2024/May/29/training-not-chatting/`: success
- `https://simonwillison.net/2024/Dec/31/llms-in-2024/`: success
- `https://www.anthropic.com/news/claude-3-5-sonnet`: success
- `https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy`: success

Conclusion:

- Baseline success rate for the network-enabled rerun: 4/4 (100%).
- No source-specific failure reproduced in the formal baseline set during this cycle.
- No code change is indicated from this maintenance pass.

Recommendation for the next cycle:

- Rerun the current formal seed set first.
- Only consider deferred candidates after another stable cycle with the current baseline set.

## 2026-05-01 directory-mode rerun

Command:

- `.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\real_seed_sources --no-persist`

Result:

- total: 5
- succeeded: 0
- failed: 5
- error: `URLError: [WinError 10013]` on each attempted URL

Judgment:

- This was a directory-mode rerun, not a pure formal-baseline-only rerun.
- The directory scan included trial/deferred material, so the `total=5` result must not be read as a formal baseline expansion.
- The formal baseline definition remains 4 URLs.
- This rerun is consistent with the current environment's network/socket restriction.
- No source-specific regression was isolated from this run.
- No code regression is implied by this failure pattern alone.
