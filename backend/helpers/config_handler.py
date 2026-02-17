import yaml

CONFIG_PATH = 'config.yaml'

def load_config() -> dict:
    with open(CONFIG_PATH, 'r') as file:
        return yaml.safe_load(file)

def load_setting(setting):
    try:
        return load_config()[setting]
    except KeyError:
        raise ValueError(f"Setting {setting} not found in config")

def set_setting(setting, value):
    config = load_config()
    config[setting] = value
    with open(CONFIG_PATH, 'w') as file:
        yaml.safe_dump(config, file)