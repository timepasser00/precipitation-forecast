"""Write the API's OpenAPI document to packages/api-contract/openapi.json (or check it is up to date).

uv run python scripts/export_openapi.py          # regenerate
uv run python scripts/export_openapi.py --check  # exit 1 if the committed file is stale
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from pf_api.app import create_app
from pf_api.settings import Settings

TARGET = Path(__file__).resolve().parents[1] / "packages" / "api-contract" / "openapi.json"


def generate() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(storage_url=tmp, serve_data=True, config_path=None))
        return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    fresh = generate()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != fresh:
            print(f"{TARGET} is out of date: run `make openapi`", file=sys.stderr)
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(fresh)
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
