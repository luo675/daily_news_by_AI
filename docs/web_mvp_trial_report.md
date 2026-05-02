# Web MVP Trial Report

Date: 2026-05-02

## Scope

Goal: build a minimal real-experience dataset and run one closed loop through import, browse, manual review, watchlist, and Ask.

This trial uses a minimal experience dataset, not a production corpus.

URL set used for this trial:

- `https://simonwillison.net/2024/May/29/training-not-chatting/`
- `https://simonwillison.net/2024/Dec/31/llms-in-2024/`
- `https://www.anthropic.com/news/claude-3-5-sonnet`
- `https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy`
- `https://www.oneusefulthing.org/p/what-openai-did`

Seed list file:

- `scripts/real_seed_sources/trial_web_mvp_closed_loop.txt`

## What Ran

1. Ran the batch importer in `--no-persist` mode first.
1. Ran the same batch with persistence enabled.
1. Opened the live Web MVP in a browser engine.
1. Created 3 watchlist items.
1. Saved 1 manual review edit.
1. Submitted 2 Ask questions and checked the returned evidence.

## Results

### Import

- `--no-persist` precheck: passed
- Batch size: 5 URLs
- Succeeded: 5
- Failed: 0
- Persistent import: passed
- Imported documents appeared in Web Dashboard and Documents pages

Imported document titles visible in Web:

- `Training is not the same as chatting: ChatGPT and other LLMs don’t remember everything you say`
- `Things we learned about LLMs in 2024`
- `Introducing Claude 3.5 Sonnet`
- `Announcing our updated Responsible Scaling Policy`
- `What OpenAI did`

### Web Browse

- Dashboard showed real counts and recent documents.
- Documents page showed a real list, not an empty shell.
- Document detail page opened for `What OpenAI did`.
- Watchlist page rendered real card state after item creation.
- Ask page rendered real question/answer history.

### Watchlist

Created items:

- `OpenAI` as a `company`
- `Anthropic` as a `company`
- `GPT-4o` as a `model`

Verification:

- Watchlist card layout was visible for all 3 items.
- Related document links were visible on the cards.

### Review

Manual edit saved:

- Target: `a0886d01-1780-4278-b53b-e301828481a3`
- Change: updated `summary_zh`, `summary_en`, and `key_points`
- Reason: `trial manual review`

Verification:

- Review page showed the saved change in history.
- The corresponding review card reflected the modified values.

### Ask

Questions submitted:

- `What did the imported OpenAI article say about GPT-4o?`
- `What did the imported Anthropic articles say about release cadence and safety policy?`

Verification:

- Both answers returned local evidence.
- Both answers showed `Evidence: 3 items`.
- Both answers were generated without requiring a real external provider as an acceptance prerequisite.

## Passed Items

- Real batch import with 5 URLs
- Web Dashboard has real content
- Web Documents has real content
- Document Detail page opens
- 3 Watchlist items created and visible as cards
- 1 Review edit saved and visible in history
- 2 Ask questions returned local evidence

## Failed Items

- None in this trial run

## Blockers / Notes

- No code changes were required for this trial.
- The browser checks were done with local Edge headless DOM inspection against the running local app.
- Some historical data already existed in the local database, so the Web pages show more than the 5 imported documents.
- Local startup command:
  - `uvicorn src.api.app:create_app --factory --reload`
- Entry points:
  - `http://127.0.0.1:8000/web`
  - `http://127.0.0.1:8000/web/dashboard`
- Suggested trial path:
  - Dashboard -> Documents -> Detail -> Review -> Watchlist -> Ask
- Known boundary:
  - The imported URLs are only a minimal experience set, not a production-quality knowledge base.
- Trial feedback format:
  - Problem page
  - Reproduction steps
  - Expected result
  - Actual result
  - Severity

## Trial Verdict

Yes, this is already close enough to hand to a user for a real体验 walkthrough.

Reason:

- The Web MVP is not an empty shell.
- At least 3 real documents are browsable.
- Watchlist, Review, and Ask all completed a working loop.
- The local evidence path is functioning end to end.

Residual caution:

- The dataset is still small and seed quality is intentionally minimal.
- This is a trial dataset, not a production-quality curated corpus.
