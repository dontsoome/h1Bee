"""H1BEE FastAPI backend entry point."""

from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent dir if it exists (local dev); in production env vars are injected directly
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import lca, jobs

app = FastAPI(title="H1BEE API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lca.router)
app.include_router(jobs.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "H1BEE API is running"}
