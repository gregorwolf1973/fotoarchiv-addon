import asyncio
import logging
import os

import uvicorn

from . import main, public

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fotoarchiv")


async def serve():
    app = main.create_app()
    ctx = app.state.ctx
    main_port = int(os.environ.get("FOTOARCHIV_PORT", "8300"))
    # proxy_headers aus: die Adresse des Gegenübers soll echt sein; Weiterleitungs-Header wertet
    # der Internetzugang selbst aus – und nur von vertrauenswürdigen Proxys
    servers = [uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=main_port, log_level="warning",
                                             access_log=False, proxy_headers=False))]
    if ctx.settings.public_enabled:
        public_app = public.create_public_app(ctx, main.STATIC_DIR)
        servers.append(uvicorn.Server(uvicorn.Config(public_app, host="0.0.0.0", port=ctx.settings.public_port,
                                                     log_level="warning", access_log=False, proxy_headers=False,
                                                     lifespan="off")))
        log.info("Internetzugang aktiv auf Port %d – nur über einen Reverse Proxy mit TLS veröffentlichen",
                 ctx.settings.public_port)
    await asyncio.gather(*(server.serve() for server in servers))


asyncio.run(serve())
