# Contributing

Thanks for contributing!

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Running

Start Chrome with CDP enabled (see README), then:

```bash
python -m clausy.server
```

## Notes

- Web UI selectors break occasionally. Keep provider selectors small and robust.
- Do not commit `profile/` (contains cookies/session).
