import yaml
import dotenv
from pathlib import Path

config_dir = Path(__file__).parent.parent.resolve() / "config"

# load .env config
config_env = dotenv.dotenv_values(config_dir / "config.env")
# load yaml config
with open(config_dir / "config.yml", "r") as f:
    config_yaml = yaml.safe_load(f)

# config parameters
openai_api_key = config_yaml["openai_api_key"]
telegram_token = config_yaml["telegram_token"]
mongodb_uri = f"mongodb://localhost:{config_env['MONGODB_PORT']}"
new_dialog_timeout = config_yaml["new_dialog_timeout"]
enable_message_streaming = config_yaml.get("enable_message_streaming", True)
return_n_generated_images = config_yaml.get("return_n_generated_images", 1)
image_size = config_yaml.get("image_size", "512x512")
n_chat_modes_per_page = config_yaml.get("n_chat_modes_per_page", 5)
allowed_telegram_usernames = config_yaml["allowed_telegram_usernames"]

bingx_api_url = config_yaml["bingx_api_url"]
dev_graphql_api = config_yaml["dev_graphql_api"]
n_strategy_per_page = config_yaml.get("n_strategy_per_page", 5)


# chat_modes
with open(config_dir / "chat_modes.yml", "r") as f:
    chat_modes = yaml.safe_load(f)
# strategy
with open(config_dir / "list_strategy.yml", "r") as f:
    strategy = yaml.safe_load(f)
# models
with open(config_dir / "models.yml", "r") as f:
    models = yaml.safe_load(f)
