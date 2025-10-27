# config.py

import os

BASE_DIR = os.path.abspath('.')
print("BASE_DIR is", BASE_DIR)

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
AE_NUX_DIR = os.path.expanduser('~/cutefishaep/AeNux')
PATCHED_FILE_FLAG = os.path.expanduser('~/cutefishaep/AeNux/patched')
PLUGIN_DIR = os.path.join(AE_NUX_DIR, "Plug-ins")
PRESET_DIR = os.path.expanduser('~/Documents/Adobe/After Effects 2024/User Presets')

WINE_PREFIX_DIR = os.path.join(BASE_DIR, "aenux", "wineprefix")
WINETRICKS_PATH = os.path.join(BASE_DIR, "winetricks")

ICON_PATH = os.path.join(BASE_DIR, "asset/logo.png")

AE_NUX_DOWNLOAD_URL = 'https://huggingface.co/cutefishae/AeNux-model/resolve/main/2024.zip'
PLUGIN_DOWNLOAD_URL = 'https://huggingface.co/cutefishae/AeNux-model/resolve/main/aenux-require-plugin.zip'

AE_NUX_ZIP_TEMP_NAME = '2024.zip'
AE_NUX_EXTRACT_DIR = 'Ae2024'
PLUGIN_ZIP_TEMP_NAME = 'aenux-require-plugin.zip'

RUNNER_BASE_DIR = os.path.join(BASE_DIR, "runner")

AENUX_COLORS_REG_CONTENT = """Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\\Control Panel\\Colors]
"ActiveBorder"="49 54 58"
"ActiveTitle"="49 54 58"
"AppWorkSpace"="60 64 72"
"Background"="49 54 58"
"ButtonAlternativeFace"="200 0 0"
"ButtonDkShadow"="154 154 154"
"ButtonFace"="49 54 58"
"ButtonHilight"="119 126 140"
"ButtonLight"="60 64 72"
"ButtonShadow"="60 64 72"
"ButtonText"="219 220 222"
"GradientActiveTitle"="49 54 58"
"GradientInactiveTitle"="49 54 58"
"GrayText"="155 155 155"
"Hilight"="119 126 140"
"HilightText"="255 255 255"
"InactiveBorder"="49 54 58"
"InactiveTitle"="49 54 58"
"InactiveTitleText"="219 220 222"
"InfoText"="159 167 180"
"InfoWindow"="49 54 58"
"Menu"="49 54 58"
"MenuBar"="49 54 58"
"MenuHilight"="119 126 140"
"MenuText"="219 220 222"
"Scrollbar"="73 78 88"
"TitleText"="219 220 222"
"Window"="35 38 41"
"WindowFrame"="49 54 58"
"WindowText"="219 220 222"
"""