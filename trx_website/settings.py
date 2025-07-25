import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).parent
TRX_RELEASE_CACHE_PATH = ROOT_DIR / "cache/releases.json"
TRX_DOCS_DIR = ROOT_DIR / "trx_docs"
STATIC_DIR = ROOT_DIR / "static"


GITHUB_ORGANIZATION = "LostArtefacts"
TRX_GITHUB_REPOSITORY = "TRX"
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
