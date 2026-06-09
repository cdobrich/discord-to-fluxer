import json
import sqlite3


class StateManager:
    """
    Manages the persistent state of the migration process using SQLite.
    Stores channel mappings, last migrated message IDs, processed categories,
    and Discord-Fluxer message ID mappings for replies, edits, and deletions.
    """

    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None
        print(f"SQLite database initialized at {self.db_file}.")

    def connect(self):
        """Establishes a connection to the SQLite database and creates tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_file)
            self.conn.row_factory = sqlite3.Row  # Allows accessing columns by name
            self.create_tables()
            print("SQLite tables checked/created.")
        except sqlite3.Error as e:
            print(f"Error connecting to SQLite database: {e}")
            raise

    def close(self):
        """Closes the connection to the SQLite database."""
        if self.conn:
            self.conn.close()
            print("SQLite database connection closed.")

    def create_tables(self):
        """Creates the necessary tables for the migration process using Fluxer naming."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_mappings (
                discord_id TEXT PRIMARY KEY,
                fluxer_id TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_mappings (
                discord_id TEXT PRIMARY KEY,
                fluxer_id TEXT NOT NULL,
                original_discord_content TEXT,
                original_discord_attachments TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emoji_mappings (
                discord_id TEXT PRIMARY KEY,
                fluxer_id TEXT NOT NULL,
                name TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS migration_status (
                channel_id TEXT PRIMARY KEY,
                last_discord_message_id TEXT NOT NULL
            )
        ''')
        self.conn.commit()

    def store_channel_mapping(self, discord_id: str, fluxer_id: str):
        """Stores or updates a channel mapping between Discord and Fluxer."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO channel_mappings (discord_id, fluxer_id)
            VALUES (?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET fluxer_id = excluded.fluxer_id
        ''', (str(discord_id), str(fluxer_id)))
        self.conn.commit()
        print(f"  [DB] Saved channel mapping: Discord {discord_id} -> Fluxer {fluxer_id}")

    def get_all_channel_mappings(self):
        """Retrieves all stored channel mappings."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT discord_id, fluxer_id FROM channel_mappings')
        return cursor.fetchall()

    def get_all_message_mappings_for_channel(self, discord_channel_id):
        """Retrieves all message mappings for a specific Discord channel."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT discord_id, fluxer_id FROM message_mappings 
            WHERE channel_discord_id = ?
        ''', (str(discord_channel_id),))
        return cursor.fetchall()

    def store_message_mapping(self, discord_id, fluxer_id, original_discord_content="",
                              original_discord_attachments=None):
        if original_discord_attachments is None:
            original_discord_attachments = []
        attachments_json = json.dumps(original_discord_attachments)
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO message_mappings (discord_id, fluxer_id, original_discord_content, original_discord_attachments)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                fluxer_id = excluded.fluxer_id,
                original_discord_content = excluded.original_discord_content,
                original_discord_attachments = excluded.original_discord_attachments
        ''', (
            str(discord_id),
            str(fluxer_id),
            original_discord_content,
            attachments_json))
        self.conn.commit()

    def update_message_record(self, discord_id, content, attachments):
        """Updates content and attachment details for tracking structural changes."""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE message_mappings 
            SET content = ?, attachments = ? 
            WHERE discord_id = ?
        ''', (content, json.dumps(attachments), str(discord_id)))
        self.conn.commit()

    def get_last_migrated_message_id(self, discord_channel_id):
        """Fetches the last successfully processed high-water mark message ID for a channel."""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT last_discord_message_id FROM migration_status WHERE channel_id = ?',
            (str(discord_channel_id),)
        )
        row = cursor.fetchone()
        return row['last_discord_message_id'] if row else None

    def store_last_migrated_message_id(self, discord_channel_id, last_message_id):
        """Updates the high-water mark message tracking state checkpoint."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO migration_status (channel_id, last_discord_message_id)
            VALUES (?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET last_discord_message_id = excluded.last_discord_message_id
        ''', (str(discord_channel_id), str(last_message_id)))
        self.conn.commit()

    def get_fluxer_message_id(self, discord_message_id):
        """Resolves a Fluxer ID from a Discord message ID (useful for replies)."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT fluxer_id FROM message_mappings WHERE discord_id = ?', (str(discord_message_id),))
        row = cursor.fetchone()
        return row['fluxer_id'] if row else None

    def get_discord_message_id(self, fluxer_message_id):
        """Resolves a Discord ID from a Fluxer message ID (useful for unpin updates)."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT discord_id FROM message_mappings WHERE fluxer_id = ?', (str(fluxer_message_id),))
        row = cursor.fetchone()
        return row['discord_id'] if row else None

    def get_message_details_by_discord_id(self, discord_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT fluxer_id, original_discord_content, original_discord_attachments FROM message_mappings WHERE discord_id = ?',
            (str(discord_id),))
        row = cursor.fetchone()
        if row:
            try:
                attachments = json.loads(row['original_discord_attachments']) if row[
                    'original_discord_attachments'] else []
            except Exception:
                attachments = []
            return {
                'fluxer_id': row['fluxer_id'],
                'original_discord_content': row['original_discord_content'],
                'original_discord_attachments': attachments
            }
        return None

    def delete_message_mapping(self, discord_message_id):
        """Removes a record when a message is synced out/deleted."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM message_mappings WHERE discord_id = ?', (str(discord_message_id),))
        self.conn.commit()

    def store_emoji_mapping(self, discord_id, fluxer_id, emoji_name):
        """Stores custom emoji associations."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO emoji_mappings (discord_id, fluxer_id, name)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET fluxer_id = excluded.fluxer_id
        ''', (str(discord_id), str(fluxer_id), emoji_name))
        self.conn.commit()

    def clear_all_data(self):
        """Clears all data from all migration-related tables."""
        print(
            "WARNING: Clearing ALL migration data from the database (channel_mappings, message_mappings, migration_status, emoji_mappings).")
        confirm = input("Are you sure you want to clear all data? Type 'yes' to confirm: ").lower()
        if confirm != 'yes':
            print("Operation cancelled. Data not cleared.")
            return False

        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM channel_mappings')
        cursor.execute('DELETE FROM message_mappings')
        cursor.execute('DELETE FROM emoji_mappings')
        cursor.execute('DELETE FROM migration_status')
        self.conn.commit()
        print("All migration data cleared from database.")
        return True