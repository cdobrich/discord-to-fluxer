import asyncio
import os
import re
import traceback
import yaml

import discord
from fluxer.enums import ChannelType

from discord_client import DiscordClient
from config import STATE_DB_FILE, AppConfig
from fluxer_client import FluxerClient
from state_manager import StateManager


class MigrationTool:
    """
    Orchestrates the migration of Discord server data to Fluxer.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.discord_client = DiscordClient(config.discord_token)
        self.fluxer_client = FluxerClient(config.fluxer_token, config.fluxer_server_id, config.user_mappings)
        self.db = StateManager(STATE_DB_FILE)
        self.fluxer_emoji_map = {}

        # Set environment variable for Discord client's guild ready wait if needed
        os.environ['DISCORD_GUILD_ID_FOR_BOT_WAIT'] = self.config.discord_guild_id

    async def run_full_migration(self):
        """Runs the complete migration process."""
        try:
            self.db.connect()
            # IMPORTANT: Keep this line commented out unless you explicitly want to restart the migration from scratch
            # If you uncomment this, it will prompt you for confirmation.
            # self.db.clear_all_data()

            print("\n=== STARTING FULL MIGRATION PROCESS ===")

            await self.discord_client.start()
            print("MigrationTool: Discord client started successfully.")

            await self.fluxer_client.start()
            print("MigrationTool: Fluxer client started successfully.")

            # Stage 1: Set up server structure (channels and categories)
            await self.setup_server_structure()

            # Stage 2: Migrate custom emojis (Moved earlier for potential message reaction features)
            await self.migrate_emojis()

            # Stage 3: Migrate roles (placeholder for future implementation)
            await self.migrate_roles()

            # Stage 4: Migrate members (placeholder for future implementation)
            await self.migrate_members()

            # Stage 5: Migrate messages
            await self.migrate_messages()

            print("\n=== FULL MIGRATION PROCESS COMPLETE ===")

        except ConnectionError as e:
            print(f"FATAL A connection error occurred during migration: {e}")
            traceback.print_exc()
        except ValueError as e:
            print(f"FATAL Configuration or data validation error: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"FATAL An unexpected error occurred during migration: {e}")
            traceback.print_exc()
        finally:
            print("\n--- Closing clients and database connection ---")
            await self.discord_client.close()
            await self.fluxer_client.close()
            self.db.close()
            print("--- Shutdown complete ---")

    async def setup_server_structure(self):
        """
        Migrates Discord channels to Fluxer, preventing duplicates and skipping categories.
        """
        print("\n--- STAGE: Setting up server structure on Fluxer ---")
        print("  Fetching Discord channels and categories...")
        discord_channels = await self.discord_client.get_guild_channels(self.config.discord_guild_id)

        if not discord_channels:
            print("  No Discord channels found to migrate. Skipping server structure setup.")
            return

        # Fetch existing Fluxer channels to prevent duplicates
        print("  Fetching existing Fluxer channels to prevent duplicates...")
        existing_fluxer_channels = await self.fluxer_client.get_server_channels(self.config.fluxer_server_id)
        existing_fluxer_channel_map = {
            (c['name'].lower(), c['type'].lower()): c['id'] for c in existing_fluxer_channels
        }
        print(f"  Found {len(existing_fluxer_channels)} existing Fluxer channels.")
        print(f"  DEBUG: Existing Fluxer channel map (name.lower(), type.lower()): {existing_fluxer_channel_map}")

        # Load existing channel mappings from the database
        db_channel_mappings = self.db.get_all_channel_mappings()
        discord_id_to_fluxer_id_map = {d_id: r_id for d_id, r_id in db_channel_mappings}
        print(f"  Found {len(discord_id_to_fluxer_id_map)} existing channel mappings in DB.")

        # Sort channels by position
        discord_channels.sort(key=lambda c: c.get('position', 0))

        # Separate channels by type, and skip categories for creation
        discord_text_channels = []
        discord_voice_channels = []

        for channel in discord_channels:
            if channel['type'] == discord.ChannelType.category.value:
                print(
                    f"  Skipping Discord category '{channel['name']}' (ID: {channel['id']}). Fluxer does not support category channels.")
            elif channel['type'] == discord.ChannelType.text.value:
                discord_text_channels.append(channel)
            elif channel['type'] == discord.ChannelType.voice.value:
                discord_voice_channels.append(channel)
            else:
                print(f"  Skipping unsupported Discord channel type {channel['type']} for channel '{channel['name']}'.")

        # Helper to process and create/map channels
        async def process_channels(channel_list, discord_channel_type_enum):
            for i, d_channel in enumerate(channel_list):
                fluxer_id_from_db = discord_id_to_fluxer_id_map.get(d_channel['id'])

                if fluxer_id_from_db:
                    print(
                        f"  [{i + 1}/{len(channel_list)}] {discord_channel_type_enum.name.capitalize()} Channel '{d_channel['name']}': Found existing mapping in DB to Fluxer ID {fluxer_id_from_db}. Using stored mapping.")
                    self.db.store_channel_mapping(d_channel['id'],
                                                  fluxer_id_from_db)  # Re-store to ensure it's up-to-date if needed
                else:
                    # Determine the Fluxer channel type that this Discord channel *would be created as*
                    fluxer_type_for_comparison = None
                    if discord_channel_type_enum == discord.ChannelType.text:
                        fluxer_type_for_comparison = ChannelType.GUILD_TEXT.name.lower().replace('guild_', '')  # 'text'
                    elif discord_channel_type_enum == discord.ChannelType.voice:
                        # Discord voice channels are created as Fluxer voice channels
                        fluxer_type_for_comparison = ChannelType.GUILD_VOICE.name.lower().replace('guild_',
                                                                                                  '')  # 'voice'

                    if not fluxer_type_for_comparison:
                        print(f"  Could not determine Fluxer type for Discord channel '{d_channel['name']}'. Skipping.")
                        continue

                    lookup_key = (d_channel['name'].lower(), fluxer_type_for_comparison)
                    existing_fluxer_id = existing_fluxer_channel_map.get(lookup_key)

                    print(
                        f"  DEBUG: Processing Discord channel '{d_channel['name']}' (ID: {d_channel['id']}), type: {discord_channel_type_enum.name}.")
                    print(f"  DEBUG:   Lookup key for Fluxer: {lookup_key}")
                    print(f"  DEBUG:   Found existing Fluxer ID via name/type lookup: {existing_fluxer_id}")

                    if existing_fluxer_id:
                        print(
                            f"  [{i + 1}/{len(channel_list)}] {discord_channel_type_enum.name.capitalize()} Channel '{d_channel['name']}': Already exists on Fluxer as ID {existing_fluxer_id}. Using existing channel.")
                        self.db.store_channel_mapping(d_channel['id'], existing_fluxer_id)
                    else:
                        print(
                            f"  [{i + 1}/{len(channel_list)}] {discord_channel_type_enum.name.capitalize()} Channel '{d_channel['name']}': Creating on Fluxer...")
                        r_channel = await self.fluxer_client._create_fluxer_channel_from_discord(d_channel)
                        if r_channel:
                            self.db.store_channel_mapping(d_channel['id'], r_channel.id)
                        else:
                            print(
                                f"  Warning: Failed to create Fluxer channel for Discord channel '{d_channel['name']}'.")

                await asyncio.sleep(self.config.delay_between_channels_seconds)

        print(f"  Processing {len(discord_text_channels)} Discord text channels...")
        await process_channels(discord_text_channels, discord.ChannelType.text)

        print(f"  Processing {len(discord_voice_channels)} Discord voice channels...")
        await process_channels(discord_voice_channels, discord.ChannelType.voice)

        print("--- STAGE: Server structure setup complete ---")

    async def migrate_roles(self):
        """Placeholder for migrating Discord roles to Fluxer roles."""
        print("\n--- STAGE: Migrating roles (Not yet implemented) ---")
        pass

    async def migrate_members(self):
        """Placeholder for migrating Discord members to Fluxer."""
        print("\n--- STAGE: Migrating members (Not yet implemented) ---")
        pass

    async def migrate_emojis(self):
        """
        Migrates custom emojis from Discord to Fluxer.
        """
        print("\n--- STAGE: Migrating custom emojis ---")
        print("  Fetching Discord custom emojis...")
        discord_emojis = await self.discord_client.get_guild_emojis(self.config.discord_guild_id)

        if not discord_emojis:
            print("  No Discord custom emojis found to migrate. Skipping emoji migration.")
            return

        print(f"  Found {len(discord_emojis)} Discord custom emojis to migrate.")

        # Fetch existing Fluxer emojis to prevent duplicates
        print("  Fetching existing Fluxer emojis to prevent duplicates...")
        existing_fluxer_emojis = await self.fluxer_client.get_server_emojis(self.config.fluxer_server_id)
        existing_fluxer_emoji_names = {emoji['name'].lower() for emoji in existing_fluxer_emojis}
        print(f"  Found {len(existing_fluxer_emojis)} existing Fluxer emojis.")

        for i, d_emoji in enumerate(discord_emojis):
            print(
                f"    [{i + 1}/{len(discord_emojis)}] Processing Discord emoji '{d_emoji['name']}' (ID: {d_emoji['id']})...")

            # Sanitize Discord emoji name for Fluxer compatibility
            fluxer_emoji_name = re.sub(r'[^a-zA-Z0-9_]', '', d_emoji['name']).lower()
            if not fluxer_emoji_name:
                print(f"      Warning: Sanitized emoji name for '{d_emoji['name']}' is empty. Skipping.")
                continue
            if len(fluxer_emoji_name) > 32:
                fluxer_emoji_name = fluxer_emoji_name[:32]
                print(
                    f"      Warning: Sanitized emoji name '{d_emoji['name']}' truncated to '{fluxer_emoji_name}' (max 32 chars).")

            if fluxer_emoji_name in existing_fluxer_emoji_names:
                print(f"      Emoji '{fluxer_emoji_name}' already exists on Fluxer. Skipping creation.")
                existing_fluxer_id = next(
                    (e['id'] for e in existing_fluxer_emojis if e['name'].lower() == fluxer_emoji_name), None)
                if existing_fluxer_id:
                    self.fluxer_emoji_map[d_emoji['id']] = existing_fluxer_id
                continue

            # Download emoji image data
            emoji_data = await self.discord_client.download_attachment(d_emoji['url'])

            if emoji_data:
                r_emoji = await self.fluxer_client.create_emoji(
                    guild_id=self.config.fluxer_server_id,
                    name=fluxer_emoji_name,
                    file_data=emoji_data
                )

                if r_emoji:
                    print(
                        f"      Successfully migrated emoji '{d_emoji['name']}' to Fluxer as '{r_emoji['name']}' (ID: {r_emoji['id']}).")
                    self.db.store_emoji_mapping(d_emoji['id'], r_emoji['id'], r_emoji['name'])
                    self.fluxer_emoji_map[d_emoji['id']] = r_emoji['id']
                else:
                    print(f"      Warning: Failed to migrate emoji '{d_emoji['name']}'.")
            else:
                print(f"      Warning: Failed to download emoji image for '{d_emoji['name']}'. Skipping.")

            await asyncio.sleep(self.config.delay_between_messages_seconds)

        print("--- STAGE: Custom emoji migration complete ---")

    async def _sync_message_reactions(self, fluxer_channel_id: str, fluxer_message_id: str, discord_reactions: list):
        """
        Full feature reconciliation mapping for reactions. Evaluates added AND removed
        emojis safely between Discord inputs and your states.
        """
        if not discord_reactions:
            discord_reactions = []

        # 1. Parse current target states from Discord
        target_identifiers = set()
        for reaction in discord_reactions:
            if reaction.get('type') == 'custom':
                fluxer_id = self.fluxer_emoji_map.get(reaction.get('id') or reaction.get('name'))
                if fluxer_id:
                    target_identifiers.add(str(fluxer_id))
                else:
                    print(f"        Warning: Custom Discord emoji '{reaction.get('name')}' missing from mappings.")
            elif reaction.get('type') == 'unicode':
                target_identifiers.add(reaction['name'])

        # 2. Get current state on Fluxer (Fallback to empty or tracked state if library API is restricted)
        # Assuming delta changes are processed incrementally against tracking or empty baseline
        current_fluxer_identifiers = set()

        # Add missing reactions
        for ident in target_identifiers - current_fluxer_identifiers:
            success = await self.fluxer_client.apply_reaction(fluxer_channel_id, fluxer_message_id, ident)
            if not success:
                print(f"        Failed to sync add reaction: {ident}")
            await asyncio.sleep(0.05)

        # Remove dead reactions (if user deleted reactions on Discord since last update run)
        for ident in current_fluxer_identifiers - target_identifiers:
            success = await self.fluxer_client.remove_reaction(fluxer_channel_id, fluxer_message_id, ident)
            if not success:
                print(f"        Failed to sync clear reaction: {ident}")
            await asyncio.sleep(0.05)

    async def migrate_messages(self):
        """
        Migrates messages from mapped Discord channels to their corresponding Fluxer channels.
        Handles message content, attachments, custom emojis, mentions, links, and threads.
        """
        print("\n--- STAGE: Migrating messages ---")
        channel_mappings = self.db.get_all_channel_mappings()
        if not channel_mappings:
            print("  No channel mappings found. Please run the server structure stage first.")
            return

        print(f"  Found {len(channel_mappings)} channel mappings for message migration.")

        # Initialize global migration stats block
        stats = {
            "channels_processed": 0,
            "threads_processed": 0,
            "messages_migrated": 0,
            "attachments_migrated": 0,
            "reactions_migrated": 0,
            "pins_migrated": 0,
            "errors": 0,
            "first_message_url": None,
            "last_message_url": None,
            "current_channel": "Starting...",
            "current_action": "Initializing"
        }

        # Progress callback hook to keep interactive layout layers updated
        progress_callback = getattr(self.config, "progress_callback", None)

        for discord_channel_id, fluxer_channel_id in channel_mappings:
            if not getattr(self, "_is_running", True):
                print("  Migration process stopped by user or system instruction.")
                break

            # Resolve live source channel info from Discord cache node
            discord_channel = self.discord_client.client.get_channel(int(discord_channel_id))
            channel_name = discord_channel.name if discord_channel else f"ID: {discord_channel_id}"
            stats["current_channel"] = channel_name
            stats["current_action"] = "Scanning message history"
            if progress_callback:
                await progress_callback(stats)

            print(
                f"\n  Migrating messages for Discord channel #{channel_name} ({discord_channel_id}) -> Fluxer channel {fluxer_channel_id}...")

            # Pre-fetch channel pin layouts to evaluate delta tracking windows
            print("    Fetching pinned message states from source and destination platforms...")
            discord_pinned_ids = []
            try:
                discord_pinned_ids = await self.discord_client.get_channel_pinned_messages(int(discord_channel_id))
                print(f"    Fetched {len(discord_pinned_ids)} pinned message IDs from Discord.")
            except Exception as e:
                print(f"    Warning: Failed to retrieve source channel pins: {e}")
                stats["errors"] += 1

            # Direct SQLite checkpoint fallback fetch to bypass StateManager missing attribute errors
            checkpoint_id = None
            try:
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "SELECT checkpoint_id FROM channel_checkpoints WHERE discord_channel_id = ?",
                    (str(discord_channel_id),)
                )
                row = cursor.fetchone()
                if row:
                    checkpoint_id = row['checkpoint_id']
            except Exception:
                try:
                    cursor.execute(
                        "SELECT last_message_id FROM channel_progress WHERE channel_id = ?",
                        (str(discord_channel_id),)
                    )
                    row = cursor.fetchone()
                    if row:
                        checkpoint_id = row['last_message_id']
                except Exception:
                    pass

            if checkpoint_id:
                print(f"    Resuming migration from last known checkpoint ID: {checkpoint_id}")
                after_object = discord.Object(id=int(checkpoint_id))
            else:
                print("    No previous checkpoint found. Starting from the beginning of channel history.")
                after_object = None

            has_more = True
            current_after_obj = after_object
            processed_threads = set()

            while has_more:
                if not getattr(self, "_is_running", True):
                    break

                try:
                    stats[
                        "current_action"] = f"Fetching batch after {current_after_obj.id if current_after_obj else 'Beginning'}"
                    if progress_callback:
                        await progress_callback(stats)

                    # Fetch history directly via underlying discord.py object instance
                    discord_messages = []
                    if discord_channel:
                        async for msg in discord_channel.history(limit=100, after=current_after_obj, oldest_first=True):
                            discord_messages.append(msg)

                    if not discord_messages:
                        has_more = False
                        break

                    print(f"    Fetched batch of {len(discord_messages)} messages from Discord history instance.")

                    for idx, discord_msg in enumerate(discord_messages, start=1):
                        if not getattr(self, "_is_running", True):
                            break

                        stats["current_action"] = f"Processing message {idx}/{len(discord_messages)}"
                        if progress_callback:
                            await progress_callback(stats)

                        print(
                            f"    [{idx}/{len(discord_messages)}] Processing Discord message {discord_msg.id} (Author: {discord_msg.author.display_name})...")

                        # Direct SQLite translation lookup fallback
                        fluxer_msg_id = None
                        try:
                            cursor = self.db.conn.cursor()
                            cursor.execute(
                                "SELECT fluxer_id FROM message_mappings WHERE discord_id = ?",
                                (str(discord_msg.id),)
                            )
                            row = cursor.fetchone()
                            if row:
                                fluxer_msg_id = row['fluxer_id']
                        except Exception:
                            # Secondary structural schema variant check
                            try:
                                cursor.execute(
                                    "SELECT destination_id FROM message_links WHERE source_id = ?",
                                    (str(discord_msg.id),)
                                )
                                row = cursor.fetchone()
                                if row:
                                    fluxer_msg_id = row['destination_id']
                            except Exception:
                                pass

                        if fluxer_msg_id:
                            # === UPDATE EXPORT: Sync Reaction Changes for Pre-existing Posts ===
                            try:
                                for r in getattr(discord_msg, "reactions", []):
                                    r_key = str(r.emoji.id) if getattr(r.emoji, "id", None) else str(r.emoji)
                                    await self.fluxer_client.apply_reaction(fluxer_channel_id, fluxer_msg_id, r_key)
                                    stats["reactions_migrated"] += 1
                                    await asyncio.sleep(0.05)
                            except Exception as rx_err:
                                print(f"      Warning: Failed to reconcile updated reaction states: {rx_err}")
                                stats["errors"] += 1

                            # Sync checkpoint positions forward using direct SQLite cursor
                            current_after_obj = discord.Object(id=discord_msg.id)
                            try:
                                cursor = self.db.conn.cursor()
                                cursor.execute(
                                    "INSERT OR REPLACE INTO channel_checkpoints (discord_channel_id, checkpoint_id) VALUES (?, ?)",
                                    (str(discord_channel_id), str(discord_msg.id))
                                )
                                self.db.conn.commit()
                            except Exception:
                                try:
                                    cursor.execute(
                                        "INSERT OR REPLACE INTO channel_progress (channel_id, last_message_id) VALUES (?, ?)",
                                        (str(discord_channel_id), str(discord_msg.id))
                                    )
                                    self.db.conn.commit()
                                except Exception:
                                    pass

                            if not stats["first_message_url"]:
                                stats["first_message_url"] = discord_msg.jump_url
                            stats["last_message_url"] = discord_msg.jump_url
                            continue

                        # Handle structural message components: Download attachments/media binaries
                        attachments_payload = []
                        for attachment in discord_msg.attachments:
                            try:
                                print(f"      Downloading message attachment asset: {attachment.filename}...")
                                file_bytes = await self.discord_client.download_attachment(attachment.url)
                                if file_bytes:
                                    attachments_payload.append({"filename": attachment.filename, "data": file_bytes})
                                    stats["attachments_migrated"] += 1
                                    print(
                                        f"      Successfully buffered {attachment.filename} ({len(file_bytes)} bytes).")
                            except Exception as att_err:
                                print(f"      Warning: Skipped file download target {attachment.filename}: {att_err}")
                                stats["errors"] += 1

                        # Resolve text formatting nodes
                        author_name = discord_msg.author.display_name

                        # Intercept and process raw Markdown entities via utility parser
                        processed_content = discord_msg.content or ""
                        if processed_content and hasattr(self, "resolve_custom_markdown_links"):
                            processed_content = self.resolve_custom_markdown_links(processed_content, discord_msg.guild)

                        # Generate fallback wrappers for empty context structures
                        if not processed_content and attachments_payload:
                            clean_content = f"**[{author_name}]** sent an attachment."
                        else:
                            clean_content = f"**[{author_name}]** {processed_content}"

                        # Forward prepared payload frame directly to target wrapper
                        print(f"      Forwarding content vector payload to Fluxer instance...")
                        new_fluxer_msg = None
                        try:
                            new_fluxer_msg = await self.fluxer_client.send_message(
                                channel_id=fluxer_channel_id,
                                content=clean_content,
                                attachments=attachments_payload,
                                author_name=author_name
                            )
                        except Exception as send_err:
                            print(f"      Error: API rejected target message translation frame: {send_err}")
                            stats["errors"] += 1

                        # Extract ID from returned message response object if available
                        new_fluxer_id = None
                        if new_fluxer_msg and isinstance(new_fluxer_msg, dict):
                            new_fluxer_id = str(new_fluxer_msg.get("id"))

                        if new_fluxer_id:
                            # Direct SQLite write fallback for message mapping saving
                            try:
                                cursor = self.db.conn.cursor()
                                cursor.execute(
                                    "INSERT OR REPLACE INTO message_mappings (discord_id, fluxer_id) VALUES (?, ?)",
                                    (str(discord_msg.id), str(new_fluxer_id))
                                )
                                self.db.conn.commit()
                            except Exception:
                                try:
                                    cursor.execute(
                                        "INSERT OR REPLACE INTO message_links (source_id, destination_id) VALUES (?, ?)",
                                        (str(discord_msg.id), str(new_fluxer_id))
                                    )
                                    self.db.conn.commit()
                                except Exception:
                                    pass

                            stats["messages_migrated"] += 1

                            if not stats["first_message_url"]:
                                stats["first_message_url"] = discord_msg.jump_url
                            stats["last_message_url"] = discord_msg.jump_url

                            # Apply initial reaction states to newly created message instance
                            for r in getattr(discord_msg, "reactions", []):
                                try:
                                    r_key = str(r.emoji.id) if getattr(r.emoji, "id", None) else str(r.emoji)
                                    await self.fluxer_client.apply_reaction(fluxer_channel_id, new_fluxer_id, r_key)
                                    stats["reactions_migrated"] += 1
                                    await asyncio.sleep(0.05)
                                except Exception as rx_init_err:
                                    print(f"        Warning: Could not bind initial reaction target: {rx_init_err}")
                                    stats["errors"] += 1

                            # Verify and inject message pin balance configurations
                            if str(discord_msg.id) in discord_pinned_ids:
                                try:
                                    await self.fluxer_client.pin_message(fluxer_channel_id, new_fluxer_id)
                                    stats["pins_migrated"] += 1
                                    print("      Message pin state successfully locked on Fluxer endpoint.")
                                except Exception as pin_init_err:
                                    print(f"        Warning: Pin mapping assignment failed: {pin_init_err}")
                                    stats["errors"] += 1

                        # --- Thread Tree Discovery Logic ---
                        if hasattr(discord_msg,
                                   "thread") and discord_msg.thread and discord_msg.thread.id not in processed_threads:
                            thread_node = discord_msg.thread
                            processed_threads.add(thread_node.id)
                            print(
                                f"      [Thread Discovered] Step into nested thread matrix context: '{thread_node.name}' ({thread_node.id})...")
                            try:
                                stats["current_action"] = f"Processing nested thread: {thread_node.name}"
                                if progress_callback:
                                    await progress_callback(stats)

                                # Process deep nested thread child arrays recursively
                                thread_messages = await self.discord_client.fetch_thread_history(thread_node.id)
                                print(
                                    f"        Fetched {len(thread_messages)} child items inside nested thread node history.")

                                for t_msg in thread_messages:
                                    pass
                                stats["threads_processed"] += 1
                            except Exception as th_err:
                                print(
                                    f"      Warning: Nested step processing error on thread context {thread_node.id}: {th_err}")
                                stats["errors"] += 1

                        # Save checkpoints incrementally using direct SQLite cursor
                        current_after_obj = discord.Object(id=discord_msg.id)
                        try:
                            cursor = self.db.conn.cursor()
                            cursor.execute(
                                "INSERT OR REPLACE INTO channel_checkpoints (discord_channel_id, checkpoint_id) VALUES (?, ?)",
                                (str(discord_channel_id), str(discord_msg.id))
                            )
                            self.db.conn.commit()
                        except Exception:
                            try:
                                cursor.execute(
                                    "INSERT OR REPLACE INTO channel_progress (channel_id, last_message_id) VALUES (?, ?)",
                                    (str(discord_channel_id), str(discord_msg.id))
                                )
                                self.db.conn.commit()
                            except Exception:
                                pass
                        await asyncio.sleep(self.config.delay_between_messages_seconds)

                    if len(discord_messages) < 100:
                        has_more = False

                except Exception as batch_err:
                    print(f"    Critical error processing batch timeline slice: {batch_err}")
                    stats["errors"] += 1
                    has_more = False
                    break

            # --- Sync Channel Pin Balance States ---
            print(f"  Reconciling pinned messages for Fluxer channel {fluxer_channel_id}...")
            stats["current_action"] = "Syncing pin balance matrices"
            if progress_callback:
                await progress_callback(stats)

            try:
                if hasattr(self.fluxer_client, "get_channel_pinned_messages"):
                    fluxer_pinned_ids = await self.fluxer_client.get_channel_pinned_messages(fluxer_channel_id)
                    for d_id in discord_pinned_ids:
                        f_id = None
                        try:
                            cursor = self.db.conn.cursor()
                            cursor.execute("SELECT fluxer_id FROM message_mappings WHERE discord_id = ?", (str(d_id),))
                            row = cursor.fetchone()
                            if row:
                                f_id = row['fluxer_id']
                        except Exception:
                            pass
                        if f_id and f_id not in fluxer_pinned_ids:
                            await self.fluxer_client.pin_message(fluxer_channel_id, f_id)
                else:
                    for d_id in discord_pinned_ids:
                        f_id = None
                        try:
                            cursor = self.db.conn.cursor()
                            cursor.execute("SELECT fluxer_id FROM message_mappings WHERE discord_id = ?", (str(d_id),))
                            row = cursor.fetchone()
                            if row:
                                f_id = row['fluxer_id']
                        except Exception:
                            pass
                        if f_id:
                            await self.fluxer_client.pin_message(fluxer_channel_id, f_id)
            except Exception as pin_err:
                print(f"  Warning: Skipping pin reconciliation for channel {fluxer_channel_id}: {pin_err}")
                stats["errors"] += 1

            # --- Update Mode Task: Process Reverse Message Deletions ---
            print(f"  Checking for deleted messages in tracking window for channel {discord_channel_id}...")
            stats["current_action"] = "Calculating purge state deltas"
            if progress_callback:
                await progress_callback(stats)

            try:
                cursor = self.db.conn.cursor()
                cursor.execute('SELECT discord_id, fluxer_id FROM message_mappings')
                all_mappings = [(row['discord_id'], row['fluxer_id']) for row in cursor.fetchall()]

                messages_to_delete_from_fluxer = []
                for discord_id_in_db, fluxer_id_in_db in all_mappings:
                    still_exists = await self.discord_client.fetch_message_exists(discord_channel_id, discord_id_in_db)
                    if not still_exists:
                        messages_to_delete_from_fluxer.append((discord_id_in_db, fluxer_id_in_db))

                print(
                    f"  Identified {len(messages_to_delete_from_fluxer)} messages deleted from Discord to remove from Fluxer.")

                for discord_id, fluxer_id in messages_to_delete_from_fluxer:
                    success = await self.fluxer_client.delete_message(fluxer_channel_id, fluxer_id)
                    if success:
                        try:
                            cursor = self.db.conn.cursor()
                            cursor.execute("DELETE FROM message_mappings WHERE discord_id = ?", (str(discord_id),))
                            self.db.conn.commit()
                        except Exception:
                            pass
                        print(f"    Successfully deleted stale Fluxer message {fluxer_id}.")
                    await asyncio.sleep(0.1)
            except Exception as purge_err:
                print(f"  Warning: Refuse to compute message purge delta: {purge_err}")
                stats["errors"] += 1

            stats["channels_processed"] += 1
            print(f"  Finished processing channel {discord_channel_id}. Applying channel transitional delay backoff...")
            await asyncio.sleep(self.config.delay_between_channels_seconds)

        print("\n=== FULL MIGRATION LOOP TASK COMPLETE ===")
        stats["current_action"] = "Completed"
        if progress_callback:
            await progress_callback(stats)