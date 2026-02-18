import json
import sqlite3


class StateManager:
    """
    Manages the persistent state of the migration process using SQLite.
    Stores channel mappings, last migrated message IDs, processed categories, and Discord-Fluxer message ID mappings for replies.
    """
    import json
    def update_message_record(self, discord_id, content, attachments):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE messages SET content = ?, attachments = ? WHERE discord_id = ?",
            (content, json.dumps(attachments), discord_id)
        )
        self.conn.commit()

    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None
        print(f"SQLite database initialized at {self.db_file}.")

    def connect(self):
        """Establishes a connection to the SQLite database and creates tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_file)
            self.conn.row_factory = sqlite3.Row # Allows accessing columns by name
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
        """Creates the necessary tables in the database."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_mappings (
                discord_id TEXT PRIMARY KEY,
                revolt_id TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_mappings (
                discord_id TEXT PRIMARY KEY,
                revolt_id TEXT,
                channel_discord_id TEXT,
                channel_revolt_id TEXT,
                original_discord_content TEXT,
                original_discord_attachments TEXT
            )
        ''')
        # Add new columns if they don't exist
        try:
            cursor.execute("ALTER TABLE message_mappings ADD COLUMN original_discord_content TEXT")
            print("Added 'original_discord_content' column to message_mappings table.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error adding column 'original_discord_content': {e}")
        try:
            cursor.execute("ALTER TABLE message_mappings ADD COLUMN original_discord_attachments TEXT")
            print("Added 'original_discord_attachments' column to message_mappings table.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error adding column 'original_discord_attachments': {e}")


        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emoji_mappings (
                discord_id TEXT PRIMARY KEY,
                revolt_id TEXT,
                name TEXT UNIQUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS migration_status (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.conn.commit()
        print("SQLite tables checked/created.")

    def store_channel_mapping(self, discord_id, fluxer_id):
        """Stores a mapping between a Discord channel ID and a Fluxer channel ID."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO channel_mappings (discord_id, revolt_id)
            VALUES (?, ?)
        ''', (discord_id, fluxer_id))
        self.conn.commit()
        print(f"Stored channel mapping: Discord {discord_id} -> Fluxer {fluxer_id}")

    def get_fluxer_channel_id(self, discord_id):
        """Retrieves the Fluxer channel ID for a given Discord channel ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT revolt_id FROM channel_mappings WHERE discord_id = ?', (discord_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def store_message_mapping(self, discord_message_id, fluxer_message_id, discord_channel_id, fluxer_channel_id, original_discord_content, original_discord_attachments):
        """
        Stores a mapping between a Discord message ID and a Fluxer message ID,
        along with their respective channel IDs, content, and attachments.
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO message_mappings (discord_id, revolt_id, channel_discord_id, channel_revolt_id, original_discord_content, original_discord_attachments)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (discord_message_id, fluxer_message_id, discord_channel_id, fluxer_channel_id, original_discord_content, json.dumps(original_discord_attachments)))
        self.conn.commit()
        # print(f"Stored message mapping: Discord {discord_message_id} -> Fluxer {fluxer_message_id}")

    def get_last_migrated_message_id(self, discord_channel_id):
        """
        Retrieves the Discord ID of the last message migrated for a specific channel.
        This helps in resuming migration from where it left off.
        """
        cursor = self.conn.cursor()
        # Order by discord_id in descending order to get the "highest" (latest) ID
        cursor.execute(
            'SELECT discord_id FROM message_mappings WHERE channel_discord_id = ? ORDER BY discord_id DESC LIMIT 1',
            (discord_channel_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_fluxer_message_id(self, discord_message_id):
        """Retrieves the Fluxer message ID for a given Discord message ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT revolt_id FROM message_mappings WHERE discord_id = ?', (discord_message_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_discord_message_id(self, fluxer_message_id):
        """Retrieves the Discord message ID for a given Fluxer message ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT discord_id FROM message_mappings WHERE revolt_id = ?', (fluxer_message_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_message_details_by_discord_id(self, discord_message_id):
        """
        Retrieves Fluxer message ID, original Discord content, and original Discord attachments
        for a given Discord message ID.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT revolt_id, original_discord_content, original_discord_attachments FROM message_mappings WHERE discord_id = ?',
            (discord_message_id,)
        )
        result = cursor.fetchone()
        if result:
            return {
                "fluxer_id": result[0],
                "original_discord_content": result[1],
                "original_discord_attachments": json.loads(result[2]) if result[2] else []
            }
        return None

    def delete_message_mapping(self, discord_message_id):
        """Deletes a message mapping from the database."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM message_mappings WHERE discord_id = ?', (discord_message_id,))
        self.conn.commit()
        print(f"Deleted message mapping for Discord ID {discord_message_id} from DB.")

    def store_emoji_mapping(self, discord_emoji_id, fluxer_emoji_id, emoji_name):
        """Stores a mapping between a Discord emoji ID and a Fluxer emoji ID."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO emoji_mappings (discord_id, revolt_id, name)
            VALUES (?, ?, ?)
        ''', (discord_emoji_id, fluxer_emoji_id, emoji_name))
        self.conn.commit()
        print(f"Stored emoji mapping: Discord {discord_emoji_id} -> Fluxer {fluxer_emoji_id} (Name: {emoji_name})")

    def get_fluxer_emoji_id(self, discord_emoji_id):
        """Retrieves the Fluxer emoji ID for a given Discord emoji ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT revolt_id FROM emoji_mappings WHERE discord_id = ?', (discord_emoji_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_migration_status(self, key):
        """Gets a general migration status value by key."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM migration_status WHERE key = ?', (key,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_all_channel_mappings(self):
        """Retrieves all stored channel mappings."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT discord_id, revolt_id FROM channel_mappings')
        return cursor.fetchall()

    def get_all_message_mappings_for_channel(self, discord_channel_id):
        """Retrieves all message mappings for a specific Discord channel."""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT discord_id, revolt_id FROM message_mappings WHERE channel_discord_id = ?',
            (discord_channel_id,)
        )
        return cursor.fetchall()

    def clear_all_data(self):
        """Clears all data from all migration-related tables. Use with extreme caution."""
        print("WARNING: Clearing ALL migration data from the database (channel_mappings, message_mappings, migration_status, emoji_mappings).")
        confirm = input("Are you sure you want to clear all data? Type 'yes' to confirm: ").lower()
        if confirm != 'yes':
            print("Operation cancelled. Data not cleared.")
            return False # Indicate that data was not cleared

        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM channel_mappings')
        cursor.execute('DELETE FROM message_mappings')
        cursor.execute('DELETE FROM emoji_mappings') # Clear emoji mappings too
        cursor.execute('DELETE FROM migration_status')
        self.conn.commit()
        print("All migration data cleared from database.")
        return True # Indicate that data was cleared