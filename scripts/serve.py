"""Launch the Video Factory ops + QC console.

  python scripts/serve.py                 # http://localhost:8310
  VF_API_PORT=9000 python scripts/serve.py

Serves the FastAPI app (backend/api.py) + the frontend SPA. Uses the sync queue by default, so it
runs fully locally with no Redis. Real generation still needs FAL_KEY in .env + Execute mode in the UI.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> int:
    import uvicorn  # noqa: E402

    host = os.environ.get("VF_API_HOST", "127.0.0.1")
    port = int(os.environ.get("VF_API_PORT", "8310"))
    url = f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}"
    print(f"Video Factory console -> {url}")
    if os.environ.get("VF_OPEN_BROWSER", "1") == "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run("backend.api:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
