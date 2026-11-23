# Brink Flair for Home Assistant

Control and monitor a Brink Flair heat recovery ventilation unit from Home
Assistant over Modbus, locally, with no cloud.

The integration is built to Home Assistant core standards and is meant to move
into core once it has proven itself. Until then it is installed through HACS.

## Supported devices

The Brink Flair range (200, 225, 300, 325, 350, 400, 450 and 600) speaks Modbus RTU
over RS-485 on its X15 connector. Home Assistant reaches it through either:

- **A Modbus TCP gateway**, such as a Waveshare RS485-to-Ethernet adapter or an
  ESP running the config in [`esphome/`](esphome/).
- **A USB RS-485 adapter** plugged into the Home Assistant machine.

Tested on: Flair 300 (appliance type 24). Other models use the same register
map, but their appliance type numbers and airflow limits still need confirming.

## Requirements

- Home Assistant 2026.9 or newer. The integration shares its Modbus connection
  through Home Assistant's built-in Modbus hub, so other integrations can use
  the same gateway.
- On the Flair, installer menu step 14: bus type **ModBus**, and note the slave
  address (14.2, factory 20), baud rate (14.3, factory 19200) and parity (14.4,
  factory even).

## Installation

1. In HACS, add `https://github.com/ysmilda/brink-flair` as a custom repository
   of type Integration, then install **Brink Flair**.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration > Brink Flair**.
4. Choose **Modbus TCP gateway** or **Serial RS-485 adapter** and enter the
   connection details. The integration reads the unit's serial number to check
   the connection before it creates the entry.

To change the connection later, use **Reconfigure** on the integration's entry.
To remove it, delete the entry from **Devices & services**.

## What you get

| Entity | Type | Notes |
| --- | --- | --- |
| Ventilation | fan | Speeds 1 to 4 (away, low, normal, high) and off. Off puts the unit in standby. The `actual_percentage` attribute shows the measured supply airflow as a percentage of the unit's max flow. |
| Airflow away / low / normal / high | number | m³/h behind each level, kept in order |
| Bypass mode | select | Automatic, closed or open |
| Bypass indoor / outdoor temperature, hysteresis | number | The automatic bypass limits |
| Filter interval | number | Days between filter warnings |
| Reset filter | button | After changing the filter |
| Filter, Fault, Frost protection | binary sensor | |
| Supply / exhaust airflow, temperature, humidity | sensor | |
| Outdoor air temperature, bypass, operating mode, filter days remaining | sensor | |
| Fan speeds, pressures, setpoints, frost status, operating hours | sensor | Diagnostic, some disabled by default |
| Humidity, CO2 sensors, preheater | sensor / binary sensor | Hidden by default. Enable the ones for parts fitted to your unit |
| Imbalance allowed, geo heat exchanger | switch | Installer settings, hidden by default |
| Supply / exhaust imbalance, geo heat exchanger min / max temperature | number | Installer settings, hidden by default |

### How control works

Choosing a speed takes over control through Modbus. While Home Assistant is in
control, the unit's display and wall switch can't change the level. The
integration can't hand control back, so once it has taken control, the display
and wall switch stay locked out.

The Flair forgets Modbus control after a power cut. The integration notices this
on its next poll and sends the level again.

## Data updates

The unit is polled every 30 seconds. After Home Assistant changes a setting, the
integration reads the unit's state back straight away, so the new value shows
once the unit has applied it. If the unit rejects a change, an error is shown and
the value stays as it was.

## Examples

- Force the bypass open on warm summer nights when it is cooler outside.
- Raise the level to high while the shower humidity is up, then set it back to normal.
- Notify when **Filter** turns on, and press **Reset filter** after the change.

## Known limitations

- Brink does not document which appliance type number belongs to which model.
  An unrecognised unit works with generic airflow limits and raises a repair
  issue asking you to report its number.
- Brink's document gives humidity in tenths of a percent, but a Flair 300
  reports whole percent, which is what the integration assumes.
- There is no fault code register. **Fault** reflects the operating mode, fan,
  frost and bypass states the unit reports.

## Troubleshooting

- **Could not reach the Flair**: check the gateway address, that step 14.1 is set
  to ModBus, and that the slave address, baud rate and parity match.
- **Entities unavailable**: the unit stopped answering. Check the RS-485 wiring
  (A to A, B to B) and the gateway's power.
- `scripts/dump_registers.py HOST` prints every documented register, which helps
  when reporting an issue.

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
```

The Modbus protocol lives in `custom_components/brink_flair/flair/`, which does
not import Home Assistant, so it can become its own PyPI library for core.

Register map source: Brink's
[Modbus UWA2-B/UWA2-E installation regulations (614882)](https://www.brinkclimatesystems.nl/documenten/modbus-uwa2-b-uwa2-e-installation-regulations-614882.pdf).
