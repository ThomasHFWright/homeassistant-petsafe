"""Constants for the PetSafe Extended integration."""

import importlib
from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN = "petsafe_extended"
ATTRIBUTION = "Data provided by the PetSafe API."
PARALLEL_UPDATES = 0

DEFAULT_UPDATE_INTERVAL_HOURS = 1
DEFAULT_ENABLE_DEBUGGING = False
DEFAULT_ENABLE_SMARTDOOR_SCHEDULES = True

CONF_REFRESH_TOKEN = "refresh_token"
CONF_ENABLE_SMARTDOOR_SCHEDULES = "enable_smartdoor_schedules"
MANUFACTURER = "PetSafe"
FEEDER_MODEL_GEN1 = "SmartFeed_1.0"
FEEDER_MODEL_GEN2 = "SmartFeed_2.0"

SERVICE_ADD_SCHEDULE = "add_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
SERVICE_DELETE_ALL_SCHEDULES = "delete_all_schedules"
SERVICE_MODIFY_SCHEDULE = "modify_schedule"
SERVICE_FEED = "feed"
SERVICE_PRIME = "prime"

ATTR_TIME = "time"
ATTR_AMOUNT = "amount"
ATTR_SLOW_FEED = "slow_feed"

RAKE_FINISHED = "RAKE_FINISHED"
CAT_IN_BOX = "CAT_IN_BOX"
ERROR_SENSOR_BLOCKED = "ERROR_SENSOR_BLOCKED"
RAKE_BUTTON_DETECTED = "RAKE_BUTTON_DETECTED"
RAKE_NOW = "RAKE_NOW"
RAKE_COUNTER_RESET = "RAKE_COUNTER_RESET"

FEED_DONE = "FEED_DONE"


def _load_optional_petsafe_const(name: str, default: str) -> str:
    """Load a petsafe-api constant without creating a static type-check dependency."""
    try:
        petsafe_const = importlib.import_module("petsafe.const")
    except ModuleNotFoundError:
        return default

    value = getattr(petsafe_const, name, default)
    return value if isinstance(value, str) else default


SMARTDOOR_MODE_MANUAL_LOCKED: Final = _load_optional_petsafe_const(
    "SMARTDOOR_MODE_MANUAL_LOCKED",
    "MANUAL_LOCKED",
)
SMARTDOOR_MODE_MANUAL_UNLOCKED: Final = _load_optional_petsafe_const(
    "SMARTDOOR_MODE_MANUAL_UNLOCKED",
    "MANUAL_UNLOCKED",
)
SMARTDOOR_MODE_SMART: Final = _load_optional_petsafe_const(
    "SMARTDOOR_MODE_SMART",
    "SMART",
)
SMARTDOOR_FINAL_ACT_LOCKED: Final = _load_optional_petsafe_const(
    "SMARTDOOR_FINAL_ACT_LOCKED",
    "LOCKED",
)
SMARTDOOR_FINAL_ACT_UNLOCKED: Final = _load_optional_petsafe_const(
    "SMARTDOOR_FINAL_ACT_UNLOCKED",
    "UNLOCKED",
)
