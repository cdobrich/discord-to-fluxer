# Discord-to-Fluxer

Migrate from Discord Chat to [Fluxer](https://github.com/fluxerapp/fluxer) chat.

You will need to create two bots (one for Discord and one for Fluxer), in order to run this program.

## TODO

Use the [Fluxer.py](https://github.com/akarealemil/fluxer.py) python API wrapper for the new API calls.
- This is available in the Python packages library (PIP or others): fluxer.py

Use the [fluxer-discord-migration](https://github.com/akarealemil/fluxer-discord-migration) `main.py` for the better workflow of asking user for input.
- Update the token gathering documentation.
- Make sure the program does not update or store the new token info.

The current `fluxer-discord-migration` app uses direct user tokens, and is not a Bot. This does work however:
- This may not be desirable in the future, since it poses possible access-risks

IDEAL SOLUTION: create a proper Fluxer Bot which can use the API to perform all the necessary steps, instead of masquerading as a user.

Official Bot Creation Guide
https://docs.fluxer.app/quickstart#step-1-set-up-your-project

### FURTHER TODO

The original Fluxer chat migrator could do an inital migration but not subsequent migrations. This glitch will need to be fixed. But after switching to using Fluxer.

## Migration Support

During the migration-proces, the data flow is from the origin Discord chat to target Fluxer server.

Migration features include:
- (from origin server to target Fluxer server) replicate all channels
- (from origin server to target Fluxer server) import custom emojis
- (from origin server to target Fluxer server) copy all prior messages in all channels, in chronological order of their creation, including attachment groups.
  - Attachments are included and correctly grouped 
  - Any Reply-to links are preserved, if possible, during copying all messages.
- (from origin server to target Fluxer server) pinned messages on all channels should be similarly pinned on the target server.

### Not Supported

Threads or Threading of conversations: This is due to a limitation of the Fluxer architecture.

#### Future Workarounds

During the migration process, dedicated suffixed `-thread` channels could be created.

## Version Support

Tested with Python 3.12, but in theory should work for older versions of Python.

## Discord Bot Setup

To enable the migration program to interact with your Discord server, your Discord bot needs specific permissions.

Follow these steps:

1.  **Create a Bot Application:**
    * Go to the [Discord Developer Portal](https://discord.com/developers/applications).
    * Log in and click on "New Application".
    * Give your application a name and create it.
    * Navigate to the "Bot" tab on the left sidebar.
    * Click "Add Bot" and confirm.

2.  **Copy Your Bot Token:**
    * Under the "Bot" tab, find the "TOKEN" section.
    * Click "Reset Token" if needed, then copy the token.
        * THIS IS NOT YOUR CLIENT SECRET. Make sure to copy THE TOKEN, ***not*** the client secret.
    * **Create a file named `discord_token.token`** (or the name specified in your `config.yaml` under `discord:token_file`) in the same directory as your migration script.
    * Paste the copied token into this file and save it. **Ensure there are no extra spaces or newlines.**

3.  **Enable Privileged Gateway Intents:**
    * Still on the "Bot" tab, scroll down to the "Privileged Gateway Intents" section.
    * Enable the **`Message Content Intent`** toggle. This is crucial for the bot to read message content and attachments.

4.  **Set Bot Permissions (OAuth2 URL Generator):**
    * Navigate to the "OAuth2" tab on the left sidebar, then select "URL Generator".
    * Under the **"SCOPES"** section, select:
        * `bot`
    * A new section titled **"BOT PERMISSIONS"** will appear. In this section, select the following permissions:
        * `View Channels`
        * `Read Message History`
    * Scroll to the very bottom of this very. A URL will have been generated. Copy the generated URL.

5.  **Invite the Bot to Your Server:**
    * Paste the copied URL into your web browser.
    * Select the Discord server you wish to migrate from (you must have "Manage Server" permissions on this server).
    * Authorize the bot.

## Stoat Bot Setup

To enable the migration program to interact with your Stoat server, your Stoat bot needs specific permissions. Follow these steps:

1.  **Create a Bot Application:**
    * Login to https://app.Fluxer.chat
    * Go to the [My Bots](https://app.Fluxer.chat/settings/bots).
    * Click "Create a Bot"
    * Copy your bot's token.
    * **Create a file named `Fluxer_token.token`** (or the name specified in your `config.yaml` under `fluxer:token_file`) in the same directory as your migration script.
    * Paste the copied token into this file and save it. **Ensure there are no extra spaces or newlines.**

2.  **Create Your Target Stoat Server:**
    * The migration program does not create new Stoat servers. You must manually create the target Stoat server where you want the Discord content to be migrated.

3.  **Invite the Bot to Your Target Server and Grant Permissions:**
    * Once your bot is created, you will need to invite it to your target Stoat server. Still on the [My Bots](https://app.Fluxer.chat/settings/bots) section:
    * Find the bot you just created.
    * Click the "Copy invite Link". This will automatically copy the target Bot's ID into a one-click link.
    * Paste the copied URL into your web browser.
    * Select the target Stoat server you wish to migrate into.
    * Click the "Add" button. There may not be any visual feedback for this action succeeding. Check your target server after a minute to verify if the new Bot is there.
    
4.  **Create Permissions to Your Stoat Bot (via Roles):**
    * Navigate to Server Settings.
    * Go to your target Stoat server.
    * Click on the server name at the top left (or right-click the server icon in the sidebar).
    * Select "Server Settings".
    * Go to the "Roles" Section.
      * In the Server Settings menu, find and click on "Roles" in the left sidebar.
      * Create a New Role for Your Bot (Recommended). Click the "Create Role" button (often a + icon or similar).
      * Give the new role a descriptive name, like "Migration Bot" or "Migrator Bot".
    * Assign Permissions to the New Role:
    * **Manage Channels:** To create new channels and categories replicating the Discord structure.
      * Temporarily enable this, if you want the bot to automatically create channels for you. This can be turned off later after initial channel creations. Or you can manually duplicate all the target channels.
    * **View Channels:** To see channels in the target server.
    * **Send Messages:** To post migrated messages.
    * **Upload Files:** To upload attachments.

5.  **Assign the Role to Your Bot:**
    * After setting the permissions for your new role, go back to the "Members" section in Server Settings.
    * Find your bot in the member list.
    * Click on your bot's entry.
    * You should see an option to assign roles to it. Select the "Migration Bot" role (or whatever you named it).
    * Save your changes.

By following these instructions, your bots will have the necessary access to perform the migration tasks.


## Server Origin and Target Server Setup


### Copy the Discord Server Channel ID

1. Log into https://discord.com/channels/
1. On the left side of the Discord Chat website, there is a sidebar. It displays the icons for servers the user (or bot) is a member of.
1. Navigate to the server by Left-clicking the original server.
1. Right-click on whatever is the original channel.
1. From the menu, select 'Copy Server ID'.

Store this server ID in the `config.yaml` file, in the `guild_id: ` section.

### Copy the Stoat Server Channel ID

1. Log into https://app.Fluxer.chat
1. On the left side of the Stoat Chat website, there is a sidebar. It displays the icons for servers the user (or bot) is a member of.
1. Navigate to the server by Left-clicking the target server.
1. Right-click on whatever is the target channel.
1. From the menu, select 'Copy server ID'.

Store this server ID in the `config.yaml` file, in the `server_id: ` section.

## Storing Credentials and IDs

Configuration is done through the `config.yaml` file in the project directory.

Stored credential files should have the `.token` extension.

## Configuration YAML File 

This program reads a `config.yaml` file, in its root program directory. This is a template example:

    discord:
      token_file: "discord_token.token"
      guild_id: "YOUR_DISCORD_SERVER_ID"
    Fluxer:
      token_file: "Fluxer_token.token"
      server_id: "YOUR_Fluxer_SERVER_ID"
    delays:
      between_messages_seconds: 0.5
      between_channels_seconds: 5.0


# Developer Notes

# Install.sh & Setup.py

Create install.sh and setup.py files, similar to your other projects.

## Multi-threading, Multi-processing and Order Preservation

The current implementation uses Python's asyncio for asynchronous operations, not traditional multi-threading.

Migrating of content from Discord channels is not multi-processed or multi-threaded, in order to preserve order of contents.

The current asynchronous design, combined with the logic of fetching messages `after_message_id` and processing them sequentially within each channel, is designed specifically to preserve chronological order:

- Channel by Channel: The program iterates through Discord channels one by one.

- Chronological Fetching: Within each channel, messages are fetched from Discord in chronological order (oldest to newest) using the after_message_id parameter.

- Sequential Posting: Each fetched message (and its attachments) is then posted to the corresponding Stoat channel sequentially. A delay is introduced after each message to prevent overwhelming the Stoat API and to further aid in maintaining order and avoiding rate limits.

## Emojis

### Feature Status
- Initial migration: DONE
- Updated changes migrated after initial migration: PENDING

The program will migrate custom emoji from Discord servers to target Stoat servers. 

If the emoji of the same name already exists on the target server, it will skip uploading. (In order to avoid duplciation.) It does not check the image contents, only the emoji name. So for example, if migrating 'kek' from Discord, but 'kek' already exists on Stoat, this emoji will be skipped.

## Preserving "Reply-to" Linkage

Reply-to links are preserved, if possible, during the migration process.

DEVELOPER NOTES: The script implements message id tracking for both origin and target servers. When the script migrates a message from Discord, it tracks the discord-message-id. When migrating and creating a Stoat message from that migration, the script also tracks the stoat-message-ID of the message, so that. Thus when the migrator encounters a later Discord message which has a reply-to-link to a prior Discord message, it can first look at the discord-message-id within the script's own database tracking. Then it will find the associated stoat-message-ID. Now when migrating this latest discord message which has a reply-to link, the migrator will create a new stoat message that uses the stoat-message-reply-to system to target the correct prior message.

# TODO / Pending Tasks

## Multi-Attachment Messages

This is a high priority critical feature.

- For multi-attachment messages, due to limitations with Stoat's current channel message display, note these were part of a series. Later this can be converted into a single combined post of multiple images.

### Roadmap

1. For the project's use-case, an intermediary migration option will be:
  - Create attachment-groups. Architecture as follows:
  - For every message which contains multiple attachments, create attachment-groups with the `original-discord-message-id + - + attachment-count` format.
    - Thread-ids must have a derivable relationship, meaning a discord-message must be able to match to a target attachment-groups.
      - It is not necessary for a attachment-groups be able to look up its original discord-message, though this might be useful for syncing both ways.
      - IMPLEMENTATION APPROACH: Store the original discord-message-id in the attachment-groups headers. 
  - LIMITATIONS: 
  - FUTURE: When multi-attachment messages is eventually added to Stoat, these attachment-groups can be converted into proper multi-attachment messages later.
1. An attempt will be made, investigating how difficult it will be to implement multi-attachment messages within the backend + frontend of Stoat.

## Contents Update Syncing

- Update the migrator to check for edited-dates on posts, indicating a post has been updated and therefore should be updated on the Stoat server

### Feature Status
  - Initial migration: 
  - Updated changes migrated after initial migration: 

## Messages

- Update contents, meaning if message text was changed or deleted, this change should be reflected in Stoat chat
- Update deleted messages, meaning if one has been erased in Discord, it should be erased in Stoat.

### Feature Status
  - Initial migration: 
  - Updated changes migrated after initial migration: 

## Misc.

- Forwarded Cross Post migrating
- Emoji reaction changes are updated

### Feature Status
  - Initial migration: 
  - Updated changes migrated after initial migration: 

## Pins

### Feature Status

- Preserve pins in channels (initial migration): DONE
- Updated changes migrated after initial migration: PENDING
  - Pinned message updates (removal or promotion, plus new messages that have been pinned)
- Preserve pins in threads: Not possible to implement until threading is implemented

## Threads

- Pinned threads within channels
- Implement and verify Thread preservation

### Roadmap

1. For the project's use-case, there are very few threads which need to be migrated. Therefore, an intermediary migration option will be:
  - Create flattened-pseudo-threads. Architecture as follows:
  - For every channel which contains any threads, create stoat-channel with the `original-channel-name + - + threads` format. Example: `#links` -> `#links-threads`
  - Migrate a thread like a normal stoat-message, but group all message top lines including a unique thread-id + ##/### position counter.
    - Thread-ids must have a derivable relationship, meaning a discord-thread must be able to match to a target stoat-pseudo-thread.
      - It is not necessary for a stoat-pseudo-thread be able to look up its original discord-thread, though this might be useful for syncing both ways.
      - IMPLEMENTATION APPROACH: Store the original discord-thread ID in the stoat-thread headers. 
  - LIMITATIONS: Any new posts to the original source thread after initial migration-stage cannot be later-added to any stoat-
  - FUTURE: When threading is eventually added to Stoat, these flattened-pseudo-threads can be converted into proper threads later.
1. An attempt will be made, investigating how difficult it will be to implement threading within the backend of Stoat.

# Testing / Unit Tests

Run the following:

    pytest -q --disable-warnings

There are many warnings from the Discord sub-libraries, which is why we suppress them.
