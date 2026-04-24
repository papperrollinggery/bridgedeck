# Contributing

## Development

This project intentionally has no Python package dependencies.

Run checks:

```bash
python3 -m py_compile bridgedeck.py
python3 bridgedeck.py --host 127.0.0.1 --port 8899
```

## Pull Request Expectations

- Keep the app local-first and dependency-light.
- Do not log or print full access tokens or refresh tokens.
- Keep full token display opt-in only.
- Back up user files before writes.
- Do not add hosted proxy behavior.
- Update `README.md` when behavior or commands change.

## Manual Test Cases

- `/api/data` returns no full tokens by default.
- `/api/data?include_secrets=1` returns full provider tokens only on explicit request.
- Non-loopback binding fails unless `--allow-remote` is passed.
- Creating a bridge provider backs up the DB/settings/auth store.
- Creating a CLI profile refuses to write into default `~/.codex`.
