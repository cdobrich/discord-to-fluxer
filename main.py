import asyncio
import argparse
import traceback

from config import load_config
from migration_tool import MigrationTool  # use the patched safe version

import logging

# Configure logging for logging
logging.basicConfig(level=logging.INFO)
# Reduce the logging level for discord.py and asyncio to INFO or WARNING
logging.getLogger('discord').setLevel(logging.INFO) # Changed from DEBUG to INFO
logging.getLogger('asyncio').setLevel(logging.INFO) # Changed from DEBUG to INFO

async def main():
    parser = argparse.ArgumentParser(description="Discord to Fluxer migration tool")
    parser.add_argument("--dry-run", action="store_true", help="Run without deleting messages")
    parser.add_argument("--delete-mode", choices=["list"], help="List candidates for deletion instead of deleting")
    parser.add_argument("--delete-mode-file", type=str, help="YAML file listing messages to delete")
    args = parser.parse_args()

    try:
        config = load_config()
        config.dry_run = args.dry_run
        config.delete_mode = args.delete_mode_file if args.delete_mode_file else args.delete_mode
    except Exception as e:
        print(f"Exiting due to configuration error: {e}")
        return

    migrator = MigrationTool(config)
    await migrator.run_full_migration()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMigration process interrupted by user.")
    except Exception as e:
        print(f"An error occurred in main execution: {e}")
        traceback.print_exc()