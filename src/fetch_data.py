"""Fetch the What's Cooking? dataset from Kaggle into data/raw/.

kagglehub downloads the competition files into its own cache; we copy the
archives into data/raw/ (gitignored) so the rest of the pipeline reads from one
stable path.

One-time prerequisites:
  - a Kaggle account;
  - accept the competition rules at
    <https://www.kaggle.com/competitions/whats-cooking/rules>;
  - expose your Kaggle API token (Kaggle -> Settings -> API -> "Create New
    Token") as KAGGLE_API_TOKEN:

        export KAGGLE_API_TOKEN="KGAT_..."    # Windows (cmd): set KAGGLE_API_TOKEN=KGAT_...
"""
import shutil
from pathlib import Path

import kagglehub

from config import COMPETITION, RAW_DIR


def fetch() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    download = Path(kagglehub.competition_download(COMPETITION))
    print(f"kagglehub cache: {download}")

    # A competition download is either a single archive or a directory of
    # archives; normalise to a list and copy each zip into data/raw/.
    archives = sorted(download.rglob("*.zip")) if download.is_dir() else [download]
    if not archives:
        raise FileNotFoundError(f"no .zip archive found under {download}")

    for archive in archives:
        destination = RAW_DIR / archive.name
        if archive.resolve() != destination.resolve():
            shutil.copy2(archive, destination)
        print(f"  -> data/raw/{destination.name}")


if __name__ == "__main__":
    fetch()
