"""Prepare the demo SQLite database for a deployment build."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Direct script execution adds ``scripts``—not the repository root—to
# ``sys.path``. Add the root explicitly so CI and deployment builds can import
# the local ``src`` package without relying on an external PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import DataLoader


def main() -> None:
    load_dotenv()
    db_path = os.getenv("DB_PATH", "data/query.db")
    data_file = os.getenv("DATA_FILE", "data/sample_ecommerce.csv")
    table_name = os.getenv("TABLE_NAME", "orders")

    if Path(db_path).exists():
        print(f"Database already exists: {db_path}")
        return

    if not Path(data_file).exists():
        raise FileNotFoundError(f"Demo data file not found: {data_file}")

    loader = DataLoader(db_path)
    try:
        info = loader.load_csv(data_file, table_name)
        print(f"Prepared {info['row_count']} rows in {db_path} ({table_name})")
    finally:
        loader.close()


if __name__ == "__main__":
    main()
