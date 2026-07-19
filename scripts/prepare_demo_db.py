"""Prepare the demo SQLite database for a deployment build."""

import os
from pathlib import Path

from dotenv import load_dotenv

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
