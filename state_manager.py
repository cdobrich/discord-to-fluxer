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

        # 1. Channel Mappings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_mappings (
                discord_id TEXT PRIMARY KEY,
                fluxer_id TEXT NOT NULL
            )
        ''')

        # 2. Message Mappings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_mappings (
                discord_id TEXT PRIMARY KEY,
                fluxer_id TEXT NOT NULL,
                channel_discord_id TEXT NOT NULL,
                channel_fluxer_id TEXT NOT NULL,
                content TEXT,
                attachments TEXT
            )
        ''')

        # 3. Emoji Mappings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emoji_mappings (
                discord_id TEXT PRIMARY KEY,
                fluxer_id TEXT NOT NULL,
                name TEXT NOT NULL
            )
        ''')

        # 4. Migration Status (Optional metadata tracking)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS migration_status (
                key TEXT PRIMARY KEY,
                value TEXT
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

    def store_message_mapping(self, discord_message_id, fluxer_message_id, discord_channel_id, fluxer_channel_id,
                              original_discord_content, original_discord_attachments):
        """Stores a message mapping for tracking edits, deletes, and replies."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO message_mappings (discord_id, fluxer_id, channel_discord_id, channel_fluxer_id, content, attachments)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET 
                content = excluded.content,
                attachments = excluded.attachments
        ''', (
            str(discord_message_id),
            str(fluxer_message_id),
            str(discord_channel_id),
            str(fluxer_channel_id),
            original_discord_content,
            json.dumps(original_discord_attachments)
        ))
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
        """Gets the highest migrated Discord message ID for a channel to resume migration."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT discord_id FROM message_mappings 
            WHERE channel_discord_id = ? 
            ORDER BY CAST(discord_id AS INTEGER) DESC LIMIT 1
        ''', (str(discord_channel_id),))
        row = cursor.fetchone()
        return row['discord_id'] if row else None

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

    def get_message_details_by_discord_id(self, discord_message_id):
        """Retrieves raw content and attachments stored for modification monitoring."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT fluxer_id, content, attachments FROM message_mappings WHERE discord_id = ?',
                       (str(discord_message_id),))
        row = cursor.fetchone()
        if row:
            return {
                'fluxer_id': row['fluxer_id'],
                'original_discord_content': row['content'],
                'original_discord_attachments': json.loads(row['attachments']) if row['attachments'] else []
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