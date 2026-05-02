# Web MVP User Trial Guide

## Start

Run:

```powershell
uvicorn src.api.app:create_app --factory --reload
```

Open:

- `http://127.0.0.1:8000/web`
- `http://127.0.0.1:8000/web/dashboard`

## Suggested Path

Follow this order:

1. Dashboard
2. Documents
3. Detail
4. Review
5. Watchlist
6. Ask

## What To Expect

- This is a minimal real-experience dataset, not a production corpus.
- Some pages will include historical data already present in the local database.
- Ask should return local evidence when the imported documents match the question.

## Report Feedback

Use this format for any issue:

- Problem page
- Reproduction steps
- Expected result
- Actual result
- Severity

## Known Boundary

- This trial demonstrates the minimal closed loop only.
- It is not a guarantee of production-scale knowledge coverage or answer quality.
