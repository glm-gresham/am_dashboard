from __future__ import annotations

import argparse

from availability_data import generate_sample_availability_data, load_snowflake_availability_data
from sqlite_repository import default_sqlite_path, replace_availability_data, repository_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the local SQLite repository used by the AM dashboard.")
    parser.add_argument(
        "--source",
        choices=("sample", "snowflake"),
        default="sample",
        help="Use sample data for local testing or Snowflake for the real data pull.",
    )
    parser.add_argument(
        "--database",
        default=str(default_sqlite_path()),
        help="Path to the SQLite repository. Defaults to local AppData on Windows.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.source == "snowflake":
        df = load_snowflake_availability_data()
    else:
        df = generate_sample_availability_data()

    database_path = replace_availability_data(df, args.database, source=args.source)
    status = repository_status(database_path)

    print(f"SQLite repository refreshed: {status['path']}")
    print(f"Rows written: {status['row_count']}")
    print(f"Source: {status.get('last_sync_source', args.source)}")
    print(f"Last sync UTC: {status.get('last_sync_utc', 'unknown')}")


if __name__ == "__main__":
    main()
