"""MUDRA backend entry point.

    python main.py            (from app/backend, with the .venv active; port 8000, or set MUDRA_PORT)
    uvicorn main:app --reload
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))  # local secrets (Google sign-in, admin emails); never committed

from mudra_api.app import create_app
from mudra_api.recordings import seed_recordings
from mudra_api.settings import RUNTIME_DIR, Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
settings = Settings()
if seeded := seed_recordings(settings.recordings_dir, RUNTIME_DIR):
    logging.getLogger("mudra").info("Copied %d packed app recordings into %s", seeded, settings.recordings_dir)
app = create_app(settings)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("MUDRA_PORT", "8000")))
