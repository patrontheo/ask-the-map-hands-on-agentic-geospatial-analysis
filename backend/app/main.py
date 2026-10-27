import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api import router
from backend.app.data import REPO_ROOT, data_dir, get_bundle

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bundle = get_bundle()
    logging.getLogger("app").info("data bundle %s: %d sites, incidents %s",
                                  data_dir(), len(bundle.sites), ", ".join(bundle.incidents))
    yield


class FrontendFiles(StaticFiles):
    """Revalidate on every load so frontend edits show up after a plain reload."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

app = FastAPI(title="Ask the Map", lifespan=lifespan)
app.include_router(router)
app.mount("/", FrontendFiles(directory=REPO_ROOT / "frontend", html=True), name="frontend")
