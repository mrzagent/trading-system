from pathlib import Path
import json

ACCOUNT_SETTINGS_PATH = Path('.account_settings.json')
print(f'Path: {ACCOUNT_SETTINGS_PATH}')
print(f'Exists: {ACCOUNT_SETTINGS_PATH.exists()}')

if ACCOUNT_SETTINGS_PATH.exists():
    with open(ACCOUNT_SETTINGS_PATH, 'r') as f:
        settings = json.load(f)
    print(f'Raw settings: {settings}')
    print(f'cooldownMinutes: {settings.get("cooldownMinutes")}')
    print(f'Converted: {settings.get("cooldownMinutes", 30)}')
