# Discord-to-Fluxer

Migrate from Discord Chat to [Fluxer](https://github.com/fluxerapp/fluxer) chat.

# Running the Program

You will need to create two bots (one for Discord and one for Fluxer), in order to run this program. This will require saving some info to files (guided steps below), running the setup script, then you may execute the full program.

Migration resuming is supported, meaning the program will resume from the last successful migrated message.
- Automatically: All channels will have a resume-attempt during the migration stage, attempting to continue from the last migrated message from each channel.

## Pre-requisites

Python 3.10 or later installed on your system.

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
    * Click "Reset Token" if needed, then copy the token value.
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

## Fluxer Bot Setup

To enable the migration program to interact with your Fluxer server, create a Fluxer bot and grant it specific permissions. Follow these steps:


1.  **Login:** Open the [Fluxer](https://web.fluxer.app/) app and sign in.

2.  **Create a Bot Application:**
    * Go to User Settings → Develoeprs → Applications. 
    * This is done by finding your user Avatar and nearby should be a Gear-icon. Click this gear-icon to access the Settings.
    * From there click the button 'Create Application'. Give the application a name.

3.  **Copy Your Bot Token:**
    * Find the section labeled "Secrets & Tokens" tab, find the "Bot token" section.
    * Click "Regenerate" button if needed, then copy the token value.
        * This seems necessary after first creating your Application regardless.
        * THIS IS NOT YOUR CLIENT SECRET. Make sure to copy THE TOKEN, ***not*** the client secret.
    * **Create a file named `fluxer_token.token`** (or the name specified in your `config.yaml` under `fluxer:token_file`) in the same directory as your migration script.
    * Paste the copied token into this file and save it. **Ensure there are no extra spaces or newlines.**


4.  **Enable Permissions:**
    * Still on the "Application" tab, scroll down to the "OAuth2 URL Builder" section.
    * Select `bot' checkbox. A new section titled **"BOT PERMISSIONS"** will appear. In this section, select the following permissions:
      * `Manage Channels`
      * `Create Emoji & Stickers`
      * `Manage Emoji & Stickers`
      * `View Channel`
      * `Send Messages`
      * `Manage Messages`
      * `Pin Messages`
      * `Embed Links`
      * `Attach Files`
      * `Read Message History`
      * `Add Reactions`
    * Scroll to the very bottom of this very. A URL will have been generated. Copy the generated URL.
    * NOTE: After selecting the minimum `bot` step, more permissions can be granted later within a target server.
    
5.  **Invite the Bot to Your Server:**
    * Paste the copied URL into your web browser.
    * Select the Fluxer server you wish to add the Bot to, in order to migrate content into there.(Your own user must have "Manage Server" permissions on this server).
    * Authorize the bot to be added.

By following these instructions, your bots will have the necessary access to perform the migration tasks.

## Server Origin and Target Server Setup


### Copy the Discord Server Channel ID

1. Log into https://discord.com/channels/
1. On the left side of the Discord Chat website, there is a sidebar. It displays the icons for servers the user (or bot) is a member of.
1. Navigate to the server by Left-clicking the original server.
1. Right-click on whatever is the original channel.
1. From the menu, select 'Copy Server ID'.

Store this server ID in the `config.yaml` file, in the `guild_id: ` section.

### Copy the Fluxer Server Channel ID

1. Log into https://web.fluxer.app/
1. On the left side of the Fluxer Chat website, there is a sidebar. It displays the icons for servers the user (or bot) is a member of.
1. Navigate to the server by Left-clicking the target server.
1. Right-click on whatever is the target channel.
1. From the menu, select 'Copy Community ID'.

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
      server_id: "YOUR_FLUXER_SERVER_ID"
    delays:
      between_messages_seconds: 0.5
      between_channels_seconds: 5.0

      
## Run the Setup.sh Script

Open a command terminal at the location where you have `Discord-to-Fluxer` code files. Run:

    sh setup.sh
  
This will create a virtual python environment and install the program's dependency files.

## Run the Exporter

Finally you are ready. To run the exporter, open a command terminal at the location where you have `Discord-to-Fluxer` code files. Run:

    source .venv/bin/python
    python main.py


# Developer Notes

## Multi-threading, Multi-processing and Order Preservation

The current implementation uses Python's asyncio for asynchronous operations, not traditional multi-threading.

Migrating of content from Discord channels is not multi-processed or multi-threaded, in order to preserve order of contents.

The current asynchronous design, combined with the logic of fetching messages `after_message_id` and processing them sequentially within each channel, is designed specifically to preserve chronological order:

- Channel by Channel: The program iterates through Discord channels one by one.

- Chronological Fetching: Within each channel, messages are fetched from Discord in chronological order (oldest to newest) using the after_message_id parameter.

- Sequential Posting: Each fetched message (and its attachments) is then posted to the corresponding Fluxer channel sequentially. A delay is introduced after each message to prevent overwhelming the Fluxer API and to further aid in maintaining order and avoiding rate limits.

# FEATURE STATUS for Migration

## Channel Creation
- Initial migration: DONE
- Updated changes migrated after initial migration: UNTESTED

## Emojis

- Initial migration: UNTESTED
- Updated changes migrated after initial migration: UNTESTED

The program will migrate custom emoji from Discord servers to target Fluxer servers. 

If the emoji of the same name already exists on the target server, it will skip uploading. (In order to avoid duplication.) It does not check the image contents, only the emoji name. So for example, if migrating 'kek' from Discord, but 'kek' already exists on Fluxer, this emoji will be skipped.

## Messages to Channels & Message Attachment

- Initial migration: DONE
- Updated changes migrated after initial migration: UNTESTED
  - RESUME: UNTESTED 

Recently received Fluxer.py library to support with messages with attachments.

- (from origin server to target Fluxer server) copy all prior messages in all channels, in chronological order of their creation, including attachment groups.
  - Attachments are included and correctly grouped 
  - Any Reply-to links are preserved, if possible, during copying all messages.

- Update contents, meaning if message text was changed or deleted, this change should be reflected in Fluxer chat
- Update deleted messages, meaning if one has been erased in Discord, it should be erased in Fluxer.

### Maximum Message Length Handling

It is possible to overrun the maximum message length when exporting a non-masqueraded message. Scenario: when export-bot will attempt to prepend a username to the delivered message.

Example:
    (sent by username Spritz) `That's a good thought` would become `Spritz: that's a good thought`

This edge-case needs to be handled.

## Messages to Channels & Message Attachment (Masquerading)

Feature to masquerade as origin server user when exporting message to target server.

- Initial migration: UNTESTED
- Updated changes migrated after initial migration: UNTESTED

## Pinned Messages / Pins

- Initial migration: UNTESTED
- Updated changes migrated after initial migration: UNTESTED
  - Pinned message updates (removal or promotion, plus new messages that have been pinned): UNTESTED
- Preserve pins in threads: Not possible to implement until threading is implemented: UNTESTED


## "Reply-to" Linkage Preserving

- Initial migration: UNTESTED
- Updated changes migrated after initial migration: UNTESTED


Reply-to links are preserved, if possible, during the migration process.

DEVELOPER NOTES: The script implements message id tracking for both origin and target servers. When the script migrates a message from Discord, it tracks the discord-message-id. When migrating and creating a Fluxer message from that migration, the script also tracks the fluxer-message-ID of the message, so that. Thus when the migrator encounters a later Discord message which has a reply-to-link to a prior Discord message, it can first look at the discord-message-id within the script's own database tracking. Then it will find the associated fluxer-message-ID. Now when migrating this latest discord message which has a reply-to link, the migrator will create a new fluxer message that uses the fluxer-message-reply-to system to target the correct prior message.

  
# Not Supported Features

Threads or Threading of conversations: This is due to a limitation of the Fluxer architecture.

## Future Workarounds

During the migration process, dedicated suffixed `-thread` channels could be created.

# Version Support

Tested with Python 3.12, but in theory should work for older versions of Python.


# Future Roadmap / Pending Tasks

## Contents Update Syncing

- Update the migrator to check for edited-dates on posts, indicating a post has been updated and therefore should be updated on the Fluxer server

## Threads

- Pinned threads within channels
- Implement and verify Thread preservation

### Roadmap

1. For the project's use-case, there are very few threads which need to be migrated. Therefore, an intermediary migration option will be:
  - Create flattened-pseudo-threads. Architecture as follows:
  - For every channel which contains any threads, create fluxer-channel with the `original-channel-name + - + threads` format. Example: `#links` -> `#links-threads`
  - Migrate a thread like a normal fluxer-message, but group all message top lines including a unique thread-id + ##/### position counter.
    - Thread-ids must have a derivable relationship, meaning a discord-thread must be able to match to a target fluxer-pseudo-thread.
      - It is not necessary for a fluxer-pseudo-thread be able to look up its original discord-thread, though this might be useful for syncing both ways.
      - IMPLEMENTATION APPROACH: Store the original discord-thread ID in the fluxer-thread headers. 
  - LIMITATIONS: Any new posts to the original source thread after initial migration-stage cannot be later-added to any fluxer-
  - FUTURE: When threading is eventually added to Fluxer, these flattened-pseudo-threads can be converted into proper threads later.
1. An attempt will be made, investigating how difficult it will be to implement threading within the backend of Fluxer.

# Testing / Unit Tests

Run the following:

    pytest -q --disable-warnings

There are many warnings from the Discord sub-libraries, which is why we suppress them.

## More Testing to Add

- make sure to export first post in channel
- reply-to message preservation
- avoid duplicating existing messages
- avoid duplicating existing emoji reactions
- add total number of messages checking during export? 
