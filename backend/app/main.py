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


app = FastAPI(title="Ask the Map", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory=REPO_ROOT / "frontend", html=True), name="frontend")
