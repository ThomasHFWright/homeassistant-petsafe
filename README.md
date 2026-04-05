# PetSafe Extended

[![GitHub Repo stars][stars-shield]][stars]
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![GitHub Activity][commits-shield]][commits]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeACoffee][bmc-shield]][bmc]

PetSafe Extended is a Home Assistant custom integration for PetSafe cloud devices. It supports SmartFeed feeders,
ScoopFree litter boxes, and SmartDoor Connected Pet Doors.

This fork builds on the original
[dcmeglio/homeassistant-petsafe](https://github.com/dcmeglio/homeassistant-petsafe) integration and adds a much
richer SmartDoor feature set, including per-pet activity, per-pet schedules, door diagnostics, and maintenance
refresh controls.

The integration uses the [`petsafe-api`](https://pypi.org/project/petsafe-api) Python package for cloud access.

## Requirements

- Home Assistant `2025.12.3` or newer for this integration
- Home Assistant `2026.3` or newer for the locally shipped `brand/` icon and logo support

## Highlights

- One config flow for PetSafe cloud login using an emailed confirmation code
- Device selection during setup for feeders, litter boxes, and SmartDoors
- SmartDoor lock, control, override, per-pet, schedule, activity, and diagnostic entities
- Optional SmartDoor schedule entities that can be turned off in integration options
- Manual maintenance refresh buttons for slow-changing schedule and pet-link data
- Feeder service actions for feeding and feeding schedule management

## Installation

### Via HACS

This repository is intended to be added as a custom HACS integration repository.

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ThomasHFWright&repository=homeassistant-petsafe&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and add this repository to HACS." /></a>

### Manual installation

1. Copy `custom_components/petsafe_extended` to `config/custom_components/petsafe_extended`.
2. Restart Home Assistant.

## Configuration

1. <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=petsafe_extended" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up PetSafe Extended." /></a>
2. Enter the email address for your PetSafe account.
3. Enter the one-time confirmation code sent by PetSafe.
4. Select which feeders, litter boxes, and SmartDoors to include.
5. Optionally enable or disable SmartDoor schedule entities in the integration options flow.

## Migration From The Original Integration

Migrating from [`dcmeglio/homeassistant-petsafe`](https://github.com/dcmeglio/homeassistant-petsafe) has breaking
changes.

- The original integration domain is `petsafe`; this fork uses `petsafe_extended`
- Home Assistant will treat this as a completely separate integration
- Existing devices and entities from the original integration are not reused or migrated
- Existing automations, dashboards, helpers, and service calls that reference the old entities will need to be
  updated

Recommended migration path:

1. Remove or uninstall the original `petsafe` integration from Home Assistant.
2. Restart Home Assistant.
3. Install `petsafe_extended` and complete setup again.
4. Re-select your feeders, litter boxes, and SmartDoors during setup.
5. Update any automations, dashboards, or scripts to use the new entity IDs and `petsafe_extended.*` service names.

For feeder and litter box users, device-side settings and cloud-stored schedules remain in your PetSafe account, but
Home Assistant will create new devices and new entities for them under this integration.

## Supported Devices

### SmartFeed feeders

Entities and controls include:

- Sensors: `Battery Level`, `Last Feeding`, `Next Feeding`, `Food Level`, `Signal Strength`
- Switches: `Feeding Paused`, `Child Lock`, `Slow Feed`
- Buttons: `Feed`, `Refresh Schedule Data`

Available service actions:

- `petsafe_extended.feed`
- `petsafe_extended.prime`
- `petsafe_extended.add_schedule`
- `petsafe_extended.modify_schedule`
- `petsafe_extended.delete_schedule`
- `petsafe_extended.delete_all_schedules`

### ScoopFree litter boxes

Entities and controls include:

- Sensors: `Rake Counter`, `Rake Status`, `Last Cleaning`, `Signal Strength`
- Selects: `Rake Timer`
- Buttons: `Clean`, `Reset`

### SmartDoor Connected Pet Doors

All SmartDoor entities attach to the same physical SmartDoor device in Home Assistant.

Core door entities:

- Lock: `Door`
- Selects: `Locked Mode`, `Smart Override`, `Power Loss Action`
- Events: door-wide `Activity`

Per-pet entities:

- Sensors: `Last Seen`, `Last Activity`
- Events: per-pet `Activity`

Optional SmartDoor schedule entities:

- Per-pet calendars: `Schedule`
- Per-pet sensors: `Smart Access`, `Next Smart Access`, `Next Smart Access Change`
- Door-level sensors: `Schedule Rule Count`, `Active Schedule Rule Count`, `Scheduled Pet Count`

SmartDoor diagnostics:

- Binary sensors: `AC Power`, `Connectivity`, `Problem`
- Sensors: `Battery Level`, `Battery Voltage`, `Signal Strength`

SmartDoor maintenance buttons:

- `Refresh Pet Data`
- `Refresh Schedule Data` when schedule entities are enabled

## SmartDoor Schedules

SmartDoor schedules are read-only in Home Assistant and are optional.

When enabled, the integration exposes:

- one schedule calendar per scheduled pet
- the current scheduled Smart access for each pet
- the next scheduled Smart access value for each pet
- the next scheduled Smart access change timestamp for each pet
- schedule summary diagnostics on the SmartDoor device

If you do not want schedule entities, disable `Enable SmartDoor schedules` in the options flow. Doing so removes the
schedule calendars and schedule-derived sensors, hides the SmartDoor `Refresh Schedule Data` button, and stops the
related schedule polling. `Refresh Pet Data`, per-pet activity, controls, and diagnostics remain available.

## SmartDoor Override

`Smart Override` temporarily applies one access mode to all pets while the door remains in Smart mode.

- Available options: `Smart Schedule`, `No access`, `Out only`, `In only`, `Full access`
- An active override clears when the next schedule event occurs
- `Smart Schedule` reflects the normal cleared state
- The PetSafe API does not currently expose a direct clear action, so an active override must expire naturally or be
  cleared in the PetSafe app

## Refresh Behavior

The integration uses different refresh cadences depending on how often the data changes:

- SmartDoor activity: every 30 seconds
- SmartDoor override state: every 30 seconds
- Feeder state and last feeding: every 60 seconds
- Litter box state and activity: every 60 seconds
- Feeder schedules: every 30 minutes
- SmartDoor schedules and preferences: every 30 minutes
- Pet directory and pet-to-device links: every 6 hours

Manual refresh options are available for slower data:

- Feeder `Refresh Schedule Data` button
- SmartDoor `Refresh Schedule Data` button
- SmartDoor `Refresh Pet Data` button
- `petsafe_extended.refresh_pet_links` service action

## Notes

- This is a cloud-polling integration.
- SmartDoor diagnostics expose power outages through `AC Power`, which turns off when the door is running on battery.
- SmartDoor `Connectivity` stays available and reports `off` when the door is offline.
- SmartDoor schedule and pet entities are added dynamically as new pets or new schedules appear.

## Credits

Thanks to [@dcmeglio](https://github.com/dcmeglio) for the original PetSafe integration that this project builds on.

[commits-shield]: https://img.shields.io/github/commit-activity/y/ThomasHFWright/homeassistant-petsafe.svg
[commits]: https://github.com/ThomasHFWright/homeassistant-petsafe/commits/master
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[license-shield]: https://img.shields.io/github/license/ThomasHFWright/homeassistant-petsafe.svg
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40ThomasHFWright-blue.svg
[releases-shield]: https://img.shields.io/github/v/release/ThomasHFWright/homeassistant-petsafe.svg
[releases]: https://github.com/ThomasHFWright/homeassistant-petsafe/releases
[stars-shield]: https://img.shields.io/github/stars/ThomasHFWright/homeassistant-petsafe.svg
[stars]: https://github.com/ThomasHFWright/homeassistant-petsafe/stargazers
[bmc-shield]: https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-yellow.svg?logo=buy-me-a-coffee
[bmc]: https://buymeacoffee.com/thomashfwright
[user_profile]: https://github.com/ThomasHFWright
