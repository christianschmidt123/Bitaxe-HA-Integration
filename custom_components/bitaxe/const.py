DOMAIN = "bitaxe"

PLATFORMS = ["sensor", "button", "update"]

ESP_MINER_RELEASE_OWNER = "bitaxeorg"
ESP_MINER_RELEASE_REPO = "ESP-Miner"
ESP_MINER_RELEASE_URL = (
    "https://api.github.com/repos/"
    f"{ESP_MINER_RELEASE_OWNER}/{ESP_MINER_RELEASE_REPO}/releases/latest"
)

FIRMWARE_ASSET_NAME = "esp-miner.bin"
# Since v2.15.0 the Web UI is embedded in the firmware binary.
# The separate www.bin asset is no longer required for official updates.
# For backward compatibility with older versions or custom UIs, we keep the endpoint
# but prioritize the unified binary.
WEB_UI_ASSET_NAME = "www.bin"

FIRMWARE_OTA_PATH = "/api/system/OTA"
WEB_UI_OTA_PATH = "/api/system/OTAWWW"
