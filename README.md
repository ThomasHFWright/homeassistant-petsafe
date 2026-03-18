# homeassistant-petsafe

[![GitHub Repo stars][stars-shield]][stars]
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![GitHub Activity][commits-shield]][commits]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeACoffee][bmc-shield]][bmc]

## PetSafe Integration for Home Assistant

Integrate your PetSafe Smartfeed feeders, Scoopfree litter boxes, and SmartDoor Connected Pet Doors into Home Assistant.

Please note I did not build any of the features of the authentication, Smartfeed feeders, or Scoopfree litter boxes workflows and I don't own a Smartfeed feeder or Scoopfree litterbox so I'll be unable to assist much with any issues regarding these. Please free to submit any pull requests regarding those features.

This integration utilises the [petsafe-api](https://pypi.org/project/petsafe-api) python package.

## Installation

### Manually

Get the folder `custom_components/petsafe` in your HA `config/custom_components`

### Via [HACS](https://hacs.xyz/)

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ThomasHFWright&repository=homeassistant-petsafe&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store." /></a>

## Configuration

1. <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=homeassistant-petsafe" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>
2. Sign in with your Petsafe credentials and choose the trackers to import.

## Contributors

Thank you to @dcmeglio for building the original [dcmeglio/homeassistant-petsafe](https://github.com/dcmeglio/homeassistant-petsafe) Home Assistant Integration. I'd be happy to have all these changes merged into your repo and hand over control. Just let me know!

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/ThomasHFWright/homeassistant-petsafe.svg
[commits]: https://github.com/ThomasHFWright/homeassistant-petsafe/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[license-shield]: https://img.shields.io/github/license/ThomasHFWright/homeassistant-petsafe.svg
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40ThomasHFWright-blue.svg
[releases-shield]: https://img.shields.io/github/v/release/ThomasHFWright/homeassistant-petsafesvg
[releases]: https://github.com/ThomasHFWright/homeassistant-petsafe/releases
[user_profile]: https://github.com/ThomasHFWright
[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[stars-shield]: https://img.shields.io/github/stars/ThomasHFWright/homeassistant-petsafe.svg
[stars]: https://github.com/ThomasHFWright/homeassistant-petsafe/stargazers
[bmc-shield]: https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-yellow.svg?logo=buy-me-a-coffee
[bmc]: https://buymeacoffee.com/thomashfwright
