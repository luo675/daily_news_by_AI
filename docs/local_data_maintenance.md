# Local Data Maintenance

This project keeps a small set of utility scripts for safe local cleanup and verification.

## Test Document Cleanup

`scripts/cleanup_test_documents.py`

Purpose:
- Remove only obvious developer verification or example documents from the local PostgreSQL database.
- Preserve real articles and user-authored local documents.

Safety rules:
- Dry-run by default.
- Only deletes when `--apply` is passed.
- Matches are conservative and limited to explicit example/test markers.
- Deletes `documents` rows only and relies on cascade behavior for related rows.

Usage:

```bash
.\.venv\Scripts\python.exe scripts/cleanup_test_documents.py
.\.venv\Scripts\python.exe scripts/cleanup_test_documents.py --apply
.\.venv\Scripts\python.exe scripts/cleanup_test_documents.py --limit 10
.\.venv\Scripts\python.exe scripts/cleanup_test_documents.py --no-include-localhost
```

