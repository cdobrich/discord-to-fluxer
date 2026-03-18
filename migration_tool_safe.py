import asyncio
import discord
import os
from fluxer.enums import ChannelType
import re
import traceback

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
        Also handles deletion of Fluxer channels if they were deleted on Discord.
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

        # --- Check for deleted channels ---
        current_discord_channel_ids = {c['id'] for c in discord_channels}
        stored_discord_channel_ids = set(discord_id_to_fluxer_id_map.keys())
        
        deleted_discord_channel_ids = stored_discord_channel_ids - current_discord_channel_ids
        
        if deleted_discord_channel_ids:
            print(f"  Found {len(deleted_discord_channel_ids)} channels in DB that are no longer on Discord. Processing deletions...")
            for d_id in deleted_discord_channel_ids:
                fluxer_id = discord_id_to_fluxer_id_map[d_id]
                print(f"    Discord channel {d_id} was deleted. Deleting corresponding Fluxer channel {fluxer_id}...")
                success = await self.fluxer_client.delete_channel(fluxer_id)
                if success:
                    print(f"      Successfully deleted Fluxer channel {fluxer_id}.")
                    self.db.delete_channel_mapping(d_id)
                else:
                    print(f"      Warning: Failed to delete Fluxer channel {fluxer_id}. It might have already been deleted manually.")
                    # Still remove from DB if it's gone or inaccessible to prevent future errors
                    self.db.delete_channel_mapping(d_id)
        # --- End deletion check ---

        # Sort channels by position
        discord_channels.sort(key=lambda c: c.get('position', 0))

        # Separate channels by type, and skip categories for creation
        discord_text_channels = []
        discord_voice_channels = []

        for channel in discord_channels:
            if channel['type'] == discord.ChannelType.category.value:
                print(f"  Skipping Discord category '{channel['name']}' (ID: {channel['id']}). Fluxer does not support category channels.")
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
                    print(f"  [{i+1}/{len(channel_list)}] {discord_channel_type_enum.name.capitalize()} Channel '{d_channel['name']}': Found existing mapping in DB to Fluxer ID {fluxer_id_from_db}. Using stored mapping.")
                    self.db.store_channel_mapping(d_channel['id'], fluxer_id_from_db) # Re-store to ensure it's up-to-date if needed
                else:
                    # Determine the Fluxer channel type that this Discord channel *would be created as*
                    fluxer_type_for_comparison = None
                    if discord_channel_type_enum == discord.ChannelType.text:
                        fluxer_type_for_comparison = ChannelType.GUILD_TEXT.name.lower().replace('guild_', '') # 'text'
                    elif discord_channel_type_enum == discord.ChannelType.voice:
                        # Discord voice channels are created as Fluxer voice channels
                        fluxer_type_for_comparison = ChannelType.GUILD_VOICE.name.lower().replace('guild_', '') # 'voice'

                    if not fluxer_type_for_comparison:
                        print(f"  Could not determine Fluxer type for Discord channel '{d_channel['name']}'. Skipping.")
                        continue

                    lookup_key = (d_channel['name'].lower(), fluxer_type_for_comparison)
                    existing_fluxer_id = existing_fluxer_channel_map.get(lookup_key)

                    print(f"  DEBUG: Processing Discord channel '{d_channel['name']}' (ID: {d_channel['id']}), type: {discord_channel_type_enum.name}.")
                    print(f"  DEBUG:   Lookup key for Fluxer: {lookup_key}")
                    print(f"  DEBUG:   Found existing Fluxer ID via name/type lookup: {existing_fluxer_id}")

                    if existing_fluxer_id:
                        print(f"  [{i+1}/{len(channel_list)}] {discord_channel_type_enum.name.capitalize()} Channel '{d_channel['name']}': Already exists on Fluxer as ID {existing_fluxer_id}. Using existing channel.")
                        self.db.store_channel_mapping(d_channel['id'], existing_fluxer_id)
                    else:
                        print(f"  [{i+1}/{len(channel_list)}] {discord_channel_type_enum.name.capitalize()} Channel '{d_channel['name']}': Creating on Fluxer...")
                        r_channel = await self.fluxer_client._create_fluxer_channel_from_discord(d_channel)
                        if r_channel:
                            self.db.store_channel_mapping(d_channel['id'], r_channel.id)
                        else:
                            print(f"  Warning: Failed to create Fluxer channel for Discord channel '{d_channel['name']}'.")

                await asyncio.sleep(self.config.delay_between_channels_seconds)

        print(f"  Processing {len(discord_text_channels)} Discord text channels...")
        await process_channels(discord_text_channels, discord.ChannelType.text)

        print(f"  Processing {len(discord_voice_channels)} Discord voice channels...")
        await process_channels(discord_voice_channels, discord.ChannelType.voice)

        print("--- STAGE: Server structure setup complete ---")

    async def migrate_roles(self):
        """
        Placeholder for migrating Discord roles to Fluxer roles.
        This would involve fetching Discord roles, creating corresponding Fluxer roles,
        and then updating member roles.
        """
        print("\n--- STAGE: Migrating roles (Not yet implemented) ---")
        # Fetch Discord roles
        # Create Fluxer roles
        # Store role mappings in DB
        # Update members' roles
        pass

    async def migrate_members(self):
        """
        Placeholder for migrating Discord members to Fluxer.
        This would involve fetching Discord members and mapping them to Fluxer users.
        Note: Bots cannot directly "migrate" users to Fluxer. This stage would
        primarily be for tracking or assigning roles to existing Fluxer users.
        """
        print("\n--- STAGE: Migrating members (Not yet implemented) ---")
        # Fetch Discord members
        # Attempt to map to existing Fluxer users (if possible, e.g., by username)
        # Store member mappings (Discord ID -> Fluxer ID) in DB
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
            print(f"    [{i+1}/{len(discord_emojis)}] Processing Discord emoji '{d_emoji['name']}' (ID: {d_emoji['id']})...")

            # Sanitize Discord emoji name for Fluxer compatibility
            # Fluxer emoji names must be alphanumeric or underscores, 1-32 characters.
            fluxer_emoji_name = re.sub(r'[^a-zA-Z0-9_]', '', d_emoji['name']).lower()
            if not fluxer_emoji_name:
                print(f"      Warning: Sanitized emoji name for '{d_emoji['name']}' is empty. Skipping.")
                continue
            if len(fluxer_emoji_name) > 32:
                fluxer_emoji_name = fluxer_emoji_name[:32]
                print(f"      Warning: Sanitized emoji name '{d_emoji['name']}' truncated to '{fluxer_emoji_name}' (max 32 chars).")

            if fluxer_emoji_name in existing_fluxer_emoji_names:
                print(f"      Emoji '{fluxer_emoji_name}' already exists on Fluxer. Skipping creation.")
                # Store existing mapping in our in-memory map for message reactions
                # Find the ID of the existing emoji from existing_fluxer_emojis
                existing_emoji_data = next((e for e in existing_fluxer_emojis if e['name'].lower() == fluxer_emoji_name), None)
                if existing_emoji_data:
                    self.fluxer_emoji_map[d_emoji['id']] = {'id': existing_emoji_data['id'], 'name': existing_emoji_data['name']}
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
                    print(f"      Successfully migrated emoji '{d_emoji['name']}' to Fluxer as '{r_emoji['name']}' (ID: {r_emoji['id']}).")
                    # Store mapping in DB and in-memory map
                    self.db.store_emoji_mapping(d_emoji['id'], r_emoji['id'], r_emoji['name'])
                    self.fluxer_emoji_map[d_emoji['id']] = {'id': r_emoji['id'], 'name': r_emoji['name']}
                else:
                    print(f"      Warning: Failed to migrate emoji '{d_emoji['name']}'. See previous errors for details (e.g., already exists, permissions, bad request).")
            else:
                print(f"      Warning: Failed to download emoji image for '{d_emoji['name']}'. Skipping.")

            await asyncio.sleep(self.config.delay_between_messages_seconds) # Use message delay for emojis too

        print("--- STAGE: Custom emoji migration complete ---")

    async def sync_reactions(self, fluxer_channel_id, fluxer_message_id, discord_reactions):
        """
        Synchronizes reactions for a message. Adds missing ones and removes extras.
        """
        # Fetch current reactions from Fluxer
        fluxer_message = await self.fluxer_client.get_message(fluxer_channel_id, fluxer_message_id)
        if not fluxer_message:
            print(f"      Warning: Could not fetch Fluxer message {fluxer_message_id} to sync reactions.")
            return

        fluxer_reactions = fluxer_message.get('reactions', {}) # dict of emoji_id -> {users: [...], me: bool}
        
        # Prepare set of Discord reactions (identifiers)
        discord_reaction_identifiers = set()
        for reaction in discord_reactions:
            if reaction['type'] == 'custom':
                fluxer_emoji_data = self.fluxer_emoji_map.get(reaction['id'])
                if fluxer_emoji_data:
                    # Identifier format for Fluxer API
                    is_animated = reaction.get('animated', False)
                    identifier = f"<{ 'a' if is_animated else '' }:{fluxer_emoji_data['name']}:{fluxer_emoji_data['id']}>"
                    discord_reaction_identifiers.add(identifier)
            elif reaction['type'] == 'unicode':
                discord_reaction_identifiers.add(reaction['name'])

        # 1. Add missing reactions
        for identifier in discord_reaction_identifiers:
            # Check if this reaction exists on Fluxer (roughly, keys might vary slightly in format so exact match is best effort)
            # Fluxer API usually returns keys like "id" for custom or unicode char
            
            # Simple check: if not in fluxer_reactions keys
            # Note: Fluxer keys for custom emojis might just be the ID.
            # We need to robustly check.
            
            already_reacted = False
            for f_key in fluxer_reactions:
                if f_key in identifier: # identifier has name:id, key might be id
                     already_reacted = True
                     break
                if f_key == identifier: # Exact match (unicode)
                    already_reacted = True
                    break
            
            if not already_reacted:
                print(f"      Sync: Adding missing reaction '{identifier}' to Fluxer message {fluxer_message_id}...")
                await self.fluxer_client.apply_reaction(fluxer_channel_id, fluxer_message_id, identifier)
                await asyncio.sleep(0.1)

        # 2. Remove extra reactions (only if 'me' is true, i.e., bot reacted)
        # Note: We can't easily remove other users' reactions without admin perms/masquerade context for everyone.
        # We'll focus on cleaning up the bot's own stale reactions.
        for f_key, info in fluxer_reactions.items():
            if info.get('me', False):
                # Check if this f_key corresponds to any current Discord reaction
                keep = False
                for d_ident in discord_reaction_identifiers:
                    if f_key in d_ident or f_key == d_ident:
                        keep = True
                        break
                
                if not keep:
                    print(f"      Sync: Removing stale reaction '{f_key}' from Fluxer message {fluxer_message_id}...")
                    await self.fluxer_client.remove_reaction(fluxer_channel_id, fluxer_message_id, f_key)
                    await asyncio.sleep(0.1)


    async def migrate_messages(self):
        """
        Migrates messages from Discord channels to corresponding Fluxer channels.
        Handles message content, attachments, and replies, and now emoji reactions.
        Also handles message edits and deletions.
        """
        print("\n--- STAGE: Migrating messages ---")
        channel_mappings = self.db.get_all_channel_mappings()
        if not channel_mappings:
            print("  No channel mappings found. Skipping message migration. Ensure channels were successfully created and mapped in the previous stage and database wasn't cleared.")
            return

        print(f"  Found {len(channel_mappings)} channel mappings for message migration.")

        for discord_channel_id, fluxer_channel_id in channel_mappings:
            # Fetch current pinned message IDs from Fluxer
            fluxer_pinned_ids = set(await self.fluxer_client.get_pinned_message_ids(fluxer_channel_id))
            full_discord_fetch_ok = True
            print(f"\n  Migrating messages for Discord channel {discord_channel_id} to Fluxer channel {fluxer_channel_id}...")

            # Get the last migrated message ID for this channel to resume
            last_migrated_discord_message_id = self.db.get_last_migrated_message_id(discord_channel_id)
            print(f"  Resuming from Discord message ID: {last_migrated_discord_message_id if last_migrated_discord_message_id else 'start'}")

            # Get all existing message mappings for this channel from the DB
            # This will be used to detect edits and deletions
            migrated_discord_ids_in_db = {
                d_id for d_id, _ in self.db.get_all_message_mappings_for_channel(discord_channel_id)
            }
            messages_currently_in_discord_channel = set() # To track messages still present in Discord

            # Fetch Discord's current pinned messages for this channel ONCE
            discord_current_pinned_ids = await self.discord_client.get_channel_pinned_messages(discord_channel_id)
            discord_current_pinned_set = set(discord_current_pinned_ids)
            print(f"  Discord currently has {len(discord_current_pinned_set)} pinned messages in this channel.")


            has_more_messages = True
            message_fetch_limit = 100 # Fetch messages in chunks

            while has_more_messages:
                try:
                    try:
                        discord_messages = await self.discord_client.get_channel_messages(
                            channel_id=discord_channel_id,
                            after_message_id=last_migrated_discord_message_id,
                            limit=message_fetch_limit
                        )

                        if not discord_messages:
                            full_discord_fetch_ok = False
                            has_more_messages = False
                            print(f"  No new messages found for Discord channel {discord_channel_id}.")
                            break

                        for i, d_message in enumerate(discord_messages):
                            print(f"    [{i+1}/{len(discord_messages)}] Processing Discord message {d_message['id']}...")
                            messages_currently_in_discord_channel.add(d_message['id']) # Add to set for deletion check

                            current_discord_content = d_message['content'] if d_message['content'] else ""
                            current_discord_attachment_urls = [att['url'] for att in d_message['attachments']]

                            fluxer_attachments = []
                            for attachment in d_message['attachments']:
                                file_data = await self.discord_client.download_attachment(attachment['url'])
                                if file_data:
                                    fluxer_attachments.append({
                                        "filename": attachment['filename'],
                                        "data": file_data
                                    })
                                    print(f"      Downloaded attachment {attachment['filename']} from Discord.")
                                else:
                                    print(f"      Warning: Failed to download attachment {attachment['filename']} from Discord.")

                            fluxer_reply_to_id = None
                            if d_message['reply_to_discord_id']:
                                fluxer_reply_to_id = self.db.get_fluxer_message_id(d_message['reply_to_discord_id'])
                                if not fluxer_reply_to_id:
                                    print(f"      Warning: Could not find Fluxer message ID for Discord reply ID {d_message['reply_to_discord_id']}. Reply will not be linked.")

                            # Construct message content, adding author info
                            author_name = d_message['author']['username']
                            if d_message['author']['discriminator'] != "0":
                                author_name += f"#{d_message['author']['discriminator']}"

                            # If there's no original content and no successful attachments,
                            # AND it's a pinned message, add placeholder content.
                            # This check now uses the discord_current_pinned_set fetched once per channel.
                            if not current_discord_content and not fluxer_attachments and not d_message['reactions']:
                                if d_message['id'] in discord_current_pinned_set: # Check against the pre-fetched set
                                    current_discord_content = "[Pinned message - original content was empty]"
                                    print(f"      Adding placeholder content for pinned Discord message {d_message['id']} to ensure migration.")
                                else:
                                    print(f"      Skipping Discord message {d_message['id']} as it has no content, no successful attachments, and no reactions.")
                                    continue

                            # --- Handle Message Edits or New Messages ---
                            db_entry = self.db.get_message_details_by_discord_id(d_message['id']) # Re-fetch to ensure current state
                            if db_entry: # Message already exists in our database, check for edits
                                stored_fluxer_id = db_entry['fluxer_id']
                                stored_content = db_entry['original_discord_content']
                                stored_attachments = db_entry['original_discord_attachments']

                                # Sync Reactions for existing messages
                                await self.sync_reactions(fluxer_channel_id, stored_fluxer_id, d_message['reactions'])

                                # Compare current Discord state with stored state
                                if current_discord_content != stored_content or set(current_discord_attachment_urls) != set(stored_attachments):
                                    print(f"      Discord message {d_message['id']} has been edited. Updating Fluxer message {stored_fluxer_id}...")
                                    
                                    # Prepare content for edit
                                    message_content_for_fluxer = f"**{author_name}** at {d_message['timestamp']}:\n{current_discord_content}"

                                    edit_success = await self.fluxer_client.edit_message(
                                        channel_id=fluxer_channel_id,
                                        message_id=stored_fluxer_id,
                                        new_content=message_content_for_fluxer,
                                        new_attachments=fluxer_attachments
                                    )
                                    if edit_success:
                                        self.db.store_message_mapping( # Update DB with new content/attachments
                                            discord_message_id=d_message['id'],
                                            fluxer_message_id=stored_fluxer_id,
                                            discord_channel_id=discord_channel_id,
                                            fluxer_channel_id=fluxer_channel_id,
                                            original_discord_content=current_discord_content,
                                            original_discord_attachments=current_discord_attachment_urls
                                        )
                                        print(f"      Successfully updated Fluxer message {stored_fluxer_id}.")
                                    else:
                                        print(f"      Warning: Failed to update Fluxer message {stored_fluxer_id}.")
                                else:
                                    print(f"      Discord message {d_message['id']} unchanged. Skipping edit.")

                            else: # New message
                                r_message = await self.fluxer_client.send_message(
                                    channel_id=fluxer_channel_id,
                                    content=current_discord_content,
                                    attachments=fluxer_attachments,
                                    author_name=author_name,
                                    reply_to_id=fluxer_reply_to_id
                                )

                                if r_message:
                                    fluxer_message_id = r_message['id']
                                    self.db.store_message_mapping(
                                        discord_message_id=d_message['id'],
                                        fluxer_message_id=fluxer_message_id,
                                        discord_channel_id=discord_channel_id,
                                        fluxer_channel_id=fluxer_channel_id,
                                        original_discord_content=current_discord_content,
                                        original_discord_attachments=current_discord_attachment_urls
                                    )
                                    last_migrated_discord_message_id = d_message['id'] # Update last migrated ID

                                    # --- Apply Reactions ---
                                    if d_message['reactions']:
                                        # Use the same logic as sync for new messages
                                        await self.sync_reactions(fluxer_channel_id, fluxer_message_id, d_message['reactions'])
                                    # --- End Apply Reactions ---

                                    # --- Pin new message if it was pinned in Discord ---
                                    if d_message['id'] in discord_current_pinned_set:
                                        print(f"      Discord message {d_message['id']} is pinned. Attempting to pin Fluxer message {fluxer_message_id}...")
                                        pin_success = await self.fluxer_client.pin_message(fluxer_channel_id, fluxer_message_id)
                                        if not pin_success:
                                            print(f"      Warning: Failed to pin newly migrated Fluxer message {fluxer_message_id}.")
                                    # --- End Pin new message ---

                                else:
                                    print(f"      Error: Failed to send message {d_message['id']} to Fluxer.")

                            await asyncio.sleep(self.config.delay_between_messages_seconds)

                        if len(discord_messages) < message_fetch_limit:
                            has_more_messages = False

                        if has_more_messages:
                            print(f"  Continuing to fetch next batch of messages for channel {discord_channel_id} from {last_migrated_discord_message_id}...")

                        await asyncio.sleep(self.config.delay_between_channels_seconds)
                    except Exception as e:
                        print(f'Error during message fetch loop: {e}')
                        full_discord_fetch_ok = False
                        has_more_messages = False
                        break

                except Exception as e:
                    print(f'Error during message fetch loop: {e}')
                    full_discord_fetch_ok = False
                    has_more_messages = False
                    break
            print(f"  Finished migrating messages for Discord channel {discord_channel_id}.")

            # --- Reconcile pinned messages (Discord -> Fluxer) ---
            try:
                discord_pinned_to_fluxer = {}
                for d_id in discord_current_pinned_set:
                    r_id = self.db.get_fluxer_message_id(d_id)
                    if r_id:
                        discord_pinned_to_fluxer[d_id] = r_id
                for d_id, r_id in discord_pinned_to_fluxer.items():
                    if r_id not in fluxer_pinned_ids:
                        print(f"  Pinning Fluxer message {r_id} for Discord pinned message {d_id}...")
                        try:
                            await self.fluxer_client.pin_message(fluxer_channel_id, r_id)
                        except Exception as e:
                            print(f"  Warning: Pin failed for Fluxer message {r_id}: {e}")
                for r_pin_id in list(fluxer_pinned_ids):
                    discord_source_id = self.db.get_discord_message_id(r_pin_id)
                    if discord_source_id and discord_source_id not in discord_current_pinned_set:
                        print(f"  Unpinning Fluxer message {r_pin_id} because Discord {discord_source_id} is not pinned...")
                        try:
                            await self.fluxer_client.unpin_message(fluxer_channel_id, r_pin_id)
                        except Exception as e:
                            print(f"  Warning: Unpin failed for Fluxer message {r_pin_id}: {e}")
            except Exception as e:
                print(f"Error reconciling pinned messages for channel {discord_channel_id}: {e}")

            # --- Reconcile edits to already-migrated messages (content and attachments) ---
            try:
                for discord_id_in_db, fluxer_id_in_db in self.db.get_all_message_mappings_for_channel(discord_channel_id):
                    d_msg = await self.discord_client.get_message_by_id(discord_channel_id, discord_id_in_db)
                    if not d_msg:
                        continue
                    
                    # Sync reactions for old messages too
                    await self.sync_reactions(fluxer_channel_id, fluxer_id_in_db, d_msg['reactions'])

                    db_entry = self.db.get_message_details_by_discord_id(discord_id_in_db)
                    if not db_entry:
                        continue
                    stored_content = db_entry['original_discord_content'] or ""
                    stored_attachments = db_entry.get('original_discord_attachments') or []
                    current_content = d_msg['content'] or ""
                    current_attachment_urls = [att['url'] for att in d_msg['attachments']]
                    if current_content != stored_content or set(current_attachment_urls) != set(stored_attachments):
                        print(f"  Detected edit on Discord message {discord_id_in_db}. Updating Fluxer message {fluxer_id_in_db}...")
                        new_fluxer_attachments = []
                        for att in d_msg['attachments']:
                            file_data = await self.discord_client.download_attachment(att['url'])
                            if file_data:
                                new_fluxer_attachments.append({
                                    "filename": att['filename'],
                                    "data": file_data
                                })
                                print(f"    Downloaded attachment {att['filename']} for edit.")
                            else:
                                print(f"    Warning: Failed to download attachment {att['filename']} during edit handling.")
                        author_name = d_msg['author']['username']
                        if d_msg['author'].get('discriminator') and d_msg['author']['discriminator'] != "0":
                            author_name += f"#{d_msg['author']['discriminator']}"
                        
                        # For edits, we keep the original format with timestamp for context.
                        message_content_for_fluxer = f"**{author_name}** at {d_msg['timestamp']}:\n{current_content}"
                        
                        edit_success = await self.fluxer_client.edit_message(
                            channel_id=fluxer_channel_id,
                            message_id=fluxer_id_in_db,
                            new_content=message_content_for_fluxer,
                            new_attachments=new_fluxer_attachments
                        )
                        if edit_success:
                            self.db.store_message_mapping(
                                discord_message_id=discord_id_in_db,
                                fluxer_message_id=fluxer_id_in_db,
                                discord_channel_id=discord_channel_id,
                                fluxer_channel_id=fluxer_channel_id,
                                original_discord_content=current_content,
                                original_discord_attachments=current_attachment_urls
                            )
                            print(f"    Updated DB for Discord {discord_id_in_db} -> Fluxer {fluxer_id_in_db}.")
                        else:
                            print(f"    Warning: Failed to edit Fluxer message {fluxer_id_in_db} for edited Discord message {discord_id_in_db}.")
            except Exception as e:
                print(f"Error reconciling edits for channel {discord_channel_id}: {e}")


            
            # --- Handle Message Deletions ---
            import yaml
            # use the value from earlier in this channel loop
            if not full_discord_fetch_ok:
                print(f"Skipping deletion check for channel {discord_channel_id} due to incomplete Discord fetch.")
                continue

            messages_to_delete_from_fluxer = []

            for discord_id_in_db, fluxer_id_in_db in self.db.get_all_message_mappings_for_channel(discord_channel_id):
                try:
                    still_exists = await self.discord_client.fetch_message_exists(discord_channel_id, discord_id_in_db)
                except Exception as e:
                    print(f"Error checking existence of Discord message {discord_id_in_db}: {e}")
                    still_exists = True

                if not still_exists:
                    messages_to_delete_from_fluxer.append((discord_id_in_db, fluxer_id_in_db))

            print(f"Identified {len(messages_to_delete_from_fluxer)} messages to delete from Fluxer for channel {discord_channel_id}.")

            if getattr(self.config, "dry_run", False):
                print(f"[Dry Run] Would delete: {messages_to_delete_from_fluxer}")
                continue

            delete_mode = getattr(self.config, "delete_mode", None)
            if delete_mode == "list":
                with open("delete_candidates.yaml", "w") as f:
                    yaml.safe_dump(messages_to_delete_from_fluxer, f)
                print("Deletion candidates written to delete_candidates.yaml")
                continue
            elif delete_mode and delete_mode.startswith("file:"):
                file_path = delete_mode.split(":", 1)[1]
                with open(file_path, "r") as f:
                    messages_to_delete_from_fluxer = yaml.safe_load(f) or []

            for discord_id, fluxer_id in messages_to_delete_from_fluxer:
                success = await self.fluxer_client.delete_message(fluxer_channel_id, fluxer_id)
                if success:
                    self.db.delete_message_mapping(discord_id)
                    print(f"Deleted Fluxer message {fluxer_id} (from Discord {discord_id})")
                else:
                    print(f"Failed to delete Fluxer message {fluxer_id} (from Discord {discord_id})")
