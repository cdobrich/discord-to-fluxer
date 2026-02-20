import yaml

CONFIG_FILE = "config.yaml"
STATE_DB_FILE = "migration_state.db"


def read_token_from_file(filepath):
    """Reads a token string from a specified file."""
    try:
        with open(filepath, 'r') as f:
            token = f.read().strip()
            if not token:
                raise ValueError(f"Token file '{filepath}' is empty.")

            # The token will now be used exactly as read from the file.
            return token
    except FileNotFoundError:
        print(f"Error: Token file '{filepath}' not found.")
        return None
    except Exception as e:
        print(f"Error reading token from '{filepath}': {e}")
        return None


class AppConfig:
    """Holds application configuration parameters."""
    def __init__(self, data):
        self.discord_token_file = data['discord'].get('token_file', "discord_token.token")
        self.fluxer_token_file = data['fluxer'].get('token_file', "fluxer_token.token")

        self.discord_token = read_token_from_file(self.discord_token_file)
        self.fluxer_token = read_token_from_file(self.fluxer_token_file)

        self.discord_guild_id = str(data['discord']['guild_id'])
        self.fluxer_server_id = str(data['fluxer']['server_id'])
        self.delay_between_messages_seconds = data['delays'].get('between_messages_seconds', 0.5)
        self.delay_between_channels_seconds = data['delays'].get('between_channels_seconds', 5.0)
        self.user_mappings = data.get('user_mappings', {})


def load_config(config_path=CONFIG_FILE):
    """Loads configuration from a YAML file."""
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        print(f"Configuration loaded from {config_path}")
        return AppConfig(config_data)
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        print("Please create a 'config.yaml' file with the following structure:")
        print('''
discord:
  token_file: "discord_token.token"
  guild_id: "YOUR_DISCORD_SERVER_ID"
fluxer:
  token_file: "fluxer_token.token"
  server_id: "YOUR_REVOLT_SERVER_ID"
delays:
  between_messages_seconds: 0.5
  between_channels_seconds: 5.0
user_mappings:
  "discord_username":
    fluxer_username: "your_fluxer_username"
    fluxer_auth_key: "your_fluxer_auth_key"
        ''')
        raise
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration file '{config_path}': {e}")
        raise
    except KeyError as e:
        print(f"Error: Missing key in configuration file: {e}. Please check your config.yaml.")
        raise
    except ValueError as e:
        print(f"Configuration error: {e}")
        raise
