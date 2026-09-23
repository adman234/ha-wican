# WiCAN for Home Assistant (preconditioning fork)

A Home Assistant integration for [WiCAN](https://github.com/meatpiHQ/wican-fw) OBD
adapters, adjusted for use with the
[wicant-i-precondition](https://github.com/L1Z3/wicant-i-precondition) firmware on
first-generation E-GMP cars (Hyundai Ioniq 5 and 6, Kia EV6, Genesis GV60).

This is a fork of [jay-oswald/ha-wican](https://github.com/jay-oswald/ha-wican), the
official WiCAN integration by Jay Oswald with contributions from meatPi. The integration
is theirs; this fork adds a few sensors and fixes for the preconditioning setup. I would
like to offer these changes back upstream, but there is no PR open for them yet. If you
run stock WiCAN firmware, use upstream.

## What is different from upstream

- **Works outside AutoPID mode.** It polls `/check_status`, so the 12V battery voltage
  and HV battery temperature work with the preconditioning firmware.
- **New sensors**: HV battery state of charge, Car Ready, Car Power State, Charging, and
  12V battery voltage shown as a primary sensor. The Charging sensor carries the raw
  `0x30E` frame as an attribute.
- **No firmware update entity.** Upstream's would offer to flash stock meatPi firmware
  over the preconditioning firmware.
- **Hostname fix.** Zeroconf hostnames kept their trailing dot (`wican_xxxx.local.`),
  which broke device URLs and the resolved-IP cache. Existing entries are repaired on the
  next restart.
- Entity names come from translations.

## Installation

1. In HACS, add `https://github.com/adman234/ha-wican` as a custom repository of type
   Integration, and install WiCAN. If upstream's version is installed, remove it first,
   since both use the `wican` domain.
2. Restart Home Assistant.

## Configuration
- In Home Assistant, go to 'Settings > Devices & Services > Integrations'.
- Click on 'Add Integration', search for WiCAN, and select it.
- Enter the mDNS/hostname (wican_xxxxxxxxxxxx.local) or IP-Address of WiCAN device to connect the WiCAN device. If you have multiple WiCAN devices repeat these steps for the other devices.
- After setup, use the WiCAN integration's *Configure* button to adjust the **Post Interval** (in seconds) that controls how often the device pushes data to Home Assistant. The default is 15 seconds.

### Webhook URL behavior
- WiCAN devices use a single local HTTP webhook URL.
- WiCAN-PRO devices on firmware `v4.49+` can receive multiple webhook URLs.
- When available, Home Assistant sends WiCAN-PRO devices a local HTTP webhook URL first and an external HTTPS webhook URL second, such as Nabu Casa or a reverse proxy.
- If no local HTTP Home Assistant URL is available, WiCAN-PRO `v4.49+` can fall back to a single external HTTPS webhook URL.

## Troubleshooting
### Not possible to add a device via IP-Address or mDNS/hostname
Potential root cause: The WiCAN device might not be accessible or the protocol is not set to "AutoPID".

To fix the issue:
1. Please make sure that the WiCAN device is accesssible from your web browser. If it is not available, ensure that it is not in sleep mode [WiCAN Docs: Sleep Mode](https://meatpihq.github.io/wican-fw/config/sleep-mode)
2. Please make sure that the WiCAN device uses protocol "AutoPID" via the WiCAN device settings.

### The device is added, but all entites show status "Unavailable"
Potential root cause: HomeAssistant has been restarted or the WiCAN integration reloaded while the WiCAN device was not available (e.g. car away, sleep mode).

To fix the issue, make sure, the WiCAN device is available (e.g. by turning on ignition of car) and then reload the integration.

### Device entities are not properly updated anymore after changing the car configuration on the WiCAN device
Potential root cause: The WiCAN integration creates entities based on the car configuration in HomeAssistant. By changing the car configuration, some PIDs might get added and others removed.

To ensure, that all entities in HomeAssistant are up to date after changing the car configuration, you can either
* delete inidividual entities, that are not available in the new car configuration OR
* delete the WiCAN device in HomeAssistant and afterwards add it again with the new car configuration.

### The Unit of measure of a device entity cannot be changed in HomeAssistant
Background: The WiCAN HomeAssistant integration creates entities based on the WiCAN car configuration.

To change the unit of measure of an entity in HomeAssistant, it needs to be updated in the WiCAN device itself:
* Open the WiCAN device in a web-browser (e.g. via link "VISIT" from the WiCAN device page in HomeAssistant)
* Go to tab "Automate", find the respective PID, update the "unit" and press "Submit changes". Further details about the car configuration are part of the official WiCAN device documentation: [Automate](https://meatpihq.github.io/wican-fw/config/automate/usage)
* After changing the unit on the WiCAN device, go to HomeAssistant and reload the WiCAN integration. This will automatically update the unit of measure for the respective entity.
