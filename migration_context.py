# migration_context.py
from discord_client import DiscordClient
from fluxer_client import FluxerClient
from state_manager import StateManager


class MigrationContext:
    def __init__(self, config, discord_client: DiscordClient, fluxer_client: FluxerClient, db: StateManager):
        self.config = config
        self.discord = discord_client
        self.fluxer = fluxer_client
        self.db = db
        self.is_running = True

        # Caches to avoid redundant DB hits during message loops
        self.message_map_cache = {}
        self.channel_map_cache = {}

    def get_fluxer_message_id(self, discord_message_id: str) -> str | None:
        """Lookup Fluxer ID from cache or database."""
        if discord_message_id in self.message_map_cache:
            return self.message_map_cache[discord_message_id]

        # Fallback to DB query
        cursor = self.db.conn.execute(
            'SELECT fluxer_id FROM message_mappings WHERE discord_id = ?',
            (str(discord_message_id),)
        )
        row = cursor.fetchone()
        if row:
            fluxer_id = str(row['fluxer_id'])
            self.message_map_cache[discord_message_id] = fluxer_id
            return fluxer_id
        return None

    def set_message_mapping(self, discord_id: str, fluxer_id: str):
        """Update both cache and database."""
        self.message_map_cache[discord_id] = str(fluxer_id)
        self.db.store_message_mapping(discord_id, fluxer_id)