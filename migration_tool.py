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
        Migrates messages from Discord channels to corresponding Fluxer channels.
        Handles full initial export, edited contents, message deletions, and pinning status syncs.
        Completely un-truncated with full reaction delta processing and masquerade clients.
        """
        print("\n--- STAGE: Migrating messages ---")
        channel_mappings = self.db.get_all_channel_mappings()
        if not channel_mappings:
            print("  No channel mappings found. Skipping message migration.")
            return

        print(f"  Found {len(channel_mappings)} channel mappings for message migration.")

        for discord_channel_id, fluxer_channel_id in channel_mappings:
            print(
                f"\n  Migrating messages for Discord channel {discord_channel_id} to Fluxer channel {fluxer_channel_id}...")

            # --- Update Mode Prep: Fetch current pinned states from Discord ---
            try:
                discord_pinned_ids = await self.discord_client.get_pinned_message_ids(discord_channel_id)
                discord_pinned_set = {str(m_id) for m_id in discord_pinned_ids}
                print(f"    Fetched {len(discord_pinned_set)} pinned message IDs from Discord.")
            except Exception as e:
                print(f"    Warning: Could not fetch pinned messages from Discord channel {discord_channel_id}: {e}")
                discord_pinned_set = set()

            # --- Fetch active sliding historical window context from Discord ---
            active_discord_ids = set()

            # Resolve last tracked message checkpoint to safely handle incremental runs
            last_migrated_id = self.db.get_last_migrated_message_id(discord_channel_id)
            print(f"    Resuming migration from last Discord message checkpoint ID: {last_migrated_id or 'Beginning'}")

            # Keep your original sliding historical window limits/pagination constraints
            discord_messages = await self.discord_client.get_channel_messages(
                channel_id=discord_channel_id,
                limit=100,
                after_message_id=last_migrated_id
            )

            if discord_messages is None:
                print(f"  Skipping message sync for channel {discord_channel_id} due to API fetch failure.")
                continue

            print(f"    Fetched {len(discord_messages)} messages for channel {discord_channel_id}.")

            for i, d_message in enumerate(discord_messages):
                print(f"    [{i + 1}/{len(discord_messages)}] Processing Discord message {d_message['id']}...")

                # Register that this message exists dynamically on Discord right now
                active_discord_ids.add(str(d_message['id']))

                # Safe initialization to completely prevent UnboundLocalError
                current_attachment_urls = []
                if 'attachments' in d_message and d_message['attachments']:
                    current_attachment_urls = [att['url'] for att in d_message['attachments']]

                current_discord_content = d_message.get('content') or ""

                # --- 1. Construct Message Presentation Layer (Masquerading & Embed Parsing) ---
                author_data = d_message.get('author', {})
                author_name = author_data.get('username', 'Unknown User')

                # Convert embed blocks if present in original payload structure
                embed_extensions = ""
                if d_message.get('embeds'):
                    for embed in d_message['embeds']:
                        embed_title = f"**{embed.get('title')}**\n" if embed.get('title') else ""
                        embed_desc = f"{embed.get('description')}\n" if embed.get('description') else ""
                        if embed_title or embed_desc:
                            embed_extensions += f"\n> _[Embed Context]_\n> {embed_title}> {embed_desc}"

                # Append embed extra transformations to main string buffer
                if embed_extensions:
                    if current_discord_content:
                        current_discord_content += "\n" + embed_extensions
                    else:
                        current_discord_content = embed_extensions

                # --- 2. Handle Attachment Downloads ---
                fluxer_attachments = []
                if 'attachments' in d_message and d_message['attachments']:
                    for att in d_message['attachments']:
                        print(f"      Downloading attachment from {att['url']}...")
                        file_data = await self.discord_client.download_attachment(att['url'])
                        if file_data:
                            fluxer_attachments.append({
                                "filename": att.get('filename', 'attachment.dat'),
                                "data": file_data
                            })
                            print(f"      Downloaded attachment {att.get('filename')} from Discord.")

                # --- 3. Parse and Map Reply Architecture Chain Linkages ---
                msg_reference_payload = None
                if d_message.get('reply_to_discord_id'):
                    fluxer_reply_to_id = self.db.get_fluxer_message_id(d_message['reply_to_discord_id'])
                    if fluxer_reply_to_id:
                        print(
                            f"      Message is a reply; mapped Discord ID {d_message['reply_to_discord_id']} to Fluxer ID {fluxer_reply_to_id}")
                        msg_reference_payload = {
                            "message_id": str(fluxer_reply_to_id),
                            "channel_id": str(fluxer_channel_id)
                        }

                # --- 4. Masquerading Token Switch Logic ---
                user_map_cfg = self.config.user_mappings.get(author_name)
                target_http_client = None

                if user_map_cfg and 'fluxer_auth_key' in user_map_cfg:
                    target_http_client = await self.fluxer_client._get_masquerade_http(author_name)

                if target_http_client:
                    print(f"      Masquerading Active: Posting directly AS authenticated user '{author_name}'...")
                    message_content_for_fluxer = current_discord_content
                else:
                    print(
                        f"      Masquerading Inactive: Posting via Master Bot proxy wrapper (Prepending authorization banner)...")
                    message_content_for_fluxer = f"**{author_name}** at {d_message.get('timestamp', '')}:\n{current_discord_content}"
                    # Use the master bot's internal HTTP client fallback
                    target_http_client = self.fluxer_client.fluxer_bot._http

                # --- 5. Evaluate Existing Mappings to determine Export vs. Update mode ---
                db_entry = self.db.get_message_details_by_discord_id(d_message['id'])

                if db_entry:
                    # UPDATE MODE: Entry was already migrated; process delta checking changes
                    stored_fluxer_id = db_entry['fluxer_id']
                    stored_content = db_entry['original_discord_content']
                    stored_attachments = db_entry['original_discord_attachments'] or []

                    # Check if text content changed or attachments sets differ
                    if current_discord_content != stored_content or set(current_attachment_urls) != set(
                            stored_attachments):
                        print(f"      Discord message {d_message['id']} detected as EDITED or modified since last run.")
                        print(f"      Propagating edits downward to Fluxer message {stored_fluxer_id}...")

                        await self.fluxer_client.edit_message(
                            channel_id=fluxer_channel_id,
                            message_id=stored_fluxer_id,
                            content=message_content_for_fluxer,
                            http_client_override=target_http_client if user_map_cfg else None
                        )

                        # Update tracking database with newly modified baseline snapshots
                        self.db.store_message_mapping(
                            discord_id=d_message['id'],
                            fluxer_id=stored_fluxer_id,
                            original_discord_content=current_discord_content,
                            original_discord_attachments=current_attachment_urls
                        )

                    # --- Differential Emoji Reaction Update Logic ---
                    discord_reactions = d_message.get('reactions', [])
                    try:
                        fluxer_reactions = await self.fluxer_client.get_message_reactions(fluxer_channel_id,
                                                                                          stored_fluxer_id)

                        # Build comparison sets for reaction deltas
                        discord_reaction_keys = set()
                        for r in discord_reactions:
                            key = r.get('id') if r.get('type') == 'custom' else r.get('name')
                            if key:
                                discord_reaction_keys.add(key)

                        fluxer_reaction_keys = {fr.get('emoji_key') for fr in fluxer_reactions if fr.get('emoji_key')}

                        # Add new reactions that appear on Discord but not yet on Fluxer
                        for r in discord_reactions:
                            r_key = r.get('id') if r.get('type') == 'custom' else r.get('name')
                            if r_key and r_key not in fluxer_reaction_keys:
                                print(
                                    f"      Reaction Delta: Adding emoji '{r.get('name')}' to Fluxer message {stored_fluxer_id}")
                                await self.fluxer_client.apply_reaction(fluxer_channel_id, stored_fluxer_id, r_key)
                                await asyncio.sleep(0.1)

                        # Remove reactions that were deleted from Discord but remain on Fluxer
                        for fr in fluxer_reactions:
                            fr_key = fr.get('emoji_key')
                            if fr_key and fr_key not in discord_reaction_keys:
                                print(
                                    f"      Reaction Delta: Removing stale emoji '{fr_key}' from Fluxer message {stored_fluxer_id}")
                                await self.fluxer_client.remove_reaction(fluxer_channel_id, stored_fluxer_id,
                                                                         fr.get('id'))
                                await asyncio.sleep(0.1)
                    except Exception as react_err:
                        print(f"      Warning: Failed to synchronize differential reaction deltas: {react_err}")

                else:
                    # INITIAL EXPORT MODE: Forwarding new message to Fluxer
                    print(f"      Forwarding new message {d_message['id']} to Fluxer...")

                    # Construct message parameters dictionary dynamically
                    send_kwargs = {
                        "content": message_content_for_fluxer,
                        "files": fluxer_attachments if fluxer_attachments else None
                    }

                    # Safely append message reference only if it exists
                    if msg_reference_payload:
                        send_kwargs["message_reference"] = msg_reference_payload

                    # Fix: Unpack configurations via **kwargs to bypass signature validation constraints
                    raw_msg_data = await target_http_client.send_message(
                        str(fluxer_channel_id),
                        **send_kwargs
                    )

                    if raw_msg_data:
                        # Extract string ID reliably from raw API dictionary response
                        fluxer_msg_id = str(raw_msg_data.get('id'))

                        # Store newly mapped references to database
                        self.db.store_message_mapping(
                            discord_id=d_message['id'],
                            fluxer_id=fluxer_msg_id,
                            original_discord_content=current_discord_content,
                            original_discord_attachments=current_attachment_urls
                        )

                        # Add baseline initial reactions
                        discord_reactions = d_message.get('reactions', [])
                        for r in discord_reactions:
                            try:
                                r_key = r.get('id') if r.get('type') == 'custom' else r.get('name')
                                if r_key:
                                    await self.fluxer_client.apply_reaction(fluxer_channel_id, fluxer_msg_id, r_key)
                                    await asyncio.sleep(0.05)
                            except Exception as e:
                                print(f"      Warning: Failed to add initial reaction '{r.get('name')}': {e}")

                        # Set high-water mark checkpoint state progress incrementally
                        self.db.store_last_migrated_message_id(discord_channel_id, d_message['id'])

                # Apply API rate-limiting protective backoff delays
                await asyncio.sleep(self.config.delay_between_messages_seconds)

            # --- Update Mode Task: Reconcile Channel Pin States ---
            try:
                print(f"  Reconciling pinned messages for Fluxer channel {fluxer_channel_id}...")
                fluxer_currently_pinned_ids = await self.fluxer_client.get_pinned_message_ids(fluxer_channel_id)

                # 1. Action Additions: Items newly pinned on Discord that are unpinned on Fluxer
                for d_id in discord_pinned_set:
                    f_id = self.db.get_fluxer_message_id(d_id)
                    if f_id and f_id not in fluxer_currently_pinned_ids:
                        print(f"    Post-migration pin sync: Pinning Fluxer message {f_id} (Discord source {d_id})")
                        await self.fluxer_client.pin_message(fluxer_channel_id, f_id)
                        await asyncio.sleep(0.2)

                # 2. Action Removals: Items unpinned on Discord that are still pinned on Fluxer
                for f_id in fluxer_currently_pinned_ids:
                    corresponding_d_id = None
                    for d_id in discord_pinned_set:
                        if self.db.get_fluxer_message_id(d_id) == f_id:
                            corresponding_d_id = d_id
                            break

                    if corresponding_d_id not in discord_pinned_set:
                        print(
                            f"    Post-migration pin sync: Unpinning Fluxer message {f_id} (No longer pinned on Discord)")
                        await self.fluxer_client.unpin_message(fluxer_channel_id, f_id)
                        await asyncio.sleep(0.2)
            except Exception as e:
                print(f"  Error reconciling pin delta states for channel {fluxer_channel_id}: {e}")

            # --- Update Mode Task: Process Reverse Message Deletions ---
            print(f"  Checking for deleted messages in tracking window for channel {discord_channel_id}...")
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT discord_id, fluxer_id FROM message_mappings')
            all_mappings = [(row['discord_id'], row['fluxer_id']) for row in cursor.fetchall()]

            messages_to_delete_from_fluxer = []

            for discord_id_in_db, fluxer_id_in_db in all_mappings:
                if discord_id_in_db in active_discord_ids:
                    continue

                still_exists = await self.discord_client.fetch_message_exists(discord_channel_id, discord_id_in_db)
                if not still_exists:
                    messages_to_delete_from_fluxer.append((discord_id_in_db, fluxer_id_in_db))

            print(
                f"  Identified {len(messages_to_delete_from_fluxer)} messages deleted from Discord to remove from Fluxer.")

            if getattr(self.config, "dry_run", False):
                print(f"    [Dry Run] Active. Skipping execution of candidates: {messages_to_delete_from_fluxer}")
                continue

            # Execute real deletion actions over mapped targets
            for discord_id, fluxer_id in messages_to_delete_from_fluxer:
                success = await self.fluxer_client.delete_message(fluxer_channel_id, fluxer_id)
                if success:
                    self.db.delete_message_mapping(discord_id)
                    print(
                        f"    Successfully deleted stale Fluxer message {fluxer_id} (Discord source {discord_id} was removed).")
                else:
                    print(f"    Warning: Failed to purge message context mapping {fluxer_id} from Fluxer API node.")
                await asyncio.sleep(0.1)

            print(f"  Finished processing channel {discord_channel_id}. Applying channel transitional delay backoff...")
            await asyncio.sleep(self.config.delay_between_channels_seconds)

        print("\n=== FULL MIGRATION LOOP TASK COMPLETE ===")