import logging
import os

import uvicorn

from .main import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

uvicorn.run(
    create_app(),
    host="0.0.0.0",
    port=int(os.environ.get("FOTOARCHIV_PORT", "8300")),
    log_level="warning",
    access_log=False,
)
