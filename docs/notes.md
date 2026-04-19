# Hardware Notes

## Board Revisions

Three hardware revisions exist. Firmware is NOT cross-compatible.

Check Settings → About for the version string:
- `1.xx.xx` — revision 1
- `2.xx.xx` — revision 2  
- `3.xx.xx` — revision 3

All revisions support manual coordinate entry: press SELECT before GPS lock → ENTER TIME/LOCATION MANUALLY.

## Known Components (Revision 1, from joshumax teardown)

| Component | Part | Notes |
|-----------|------|-------|
| CPU | Samsung S3C2410AL-20 | ARM920T, 135MHz |
| NAND | Samsung K9F5608U0D | 32MB |
| RAM | Samsung K4S641632N | 64MB |
| GPS | SkyLab SKG13C | SIRF chipset, Motorola OnCore protocol |
| OS | ucOS II | Built with ADS (ARM Developer Suite) |

## Debug UART

Three test points near the CPU:

| Pin | Function |
|-----|----------|
| TP16 | GND |
| TP17 | TXD (device transmits) |
| TP18 | RXD (device receives) |

Settings: **9600 baud, 8N1**

Connect with any USB-UART adapter (CP2102, CH340, FTDI).

Boot log output includes full system initialisation, sensor calibration values, and a debug shell prompt `$`.

### Debug shell commands (from joshumax)

```
help          - list all commands
hwrtc -g      - get hardware RTC date/time
hwrtc -s yyyy.m.d.h.m.s  - set hardware RTC
nvdata        - access non-volatile flash data
nvdump        - dump NVData area
gpsShow       - print GPS messages in human-readable form (used by DM2NT to decode protocol)
getSensorVectors - raw sensor output
getOrientation   - computed pointing
getBatteryLevel
getTemperature
TaskDump      - show running OS tasks
heapstats     - heap statistics
```

## GPS Chip

The SkyLab SKG13C uses a **SIRF chipset** speaking a proprietary variant of the **Motorola OnCore binary protocol**.

Protocol details (reverse engineered by DM2NT, February 2026):

- UART: **19560 baud** (non-standard), 3.3V, 8N1
- Packet format: `@@ ID1 ID2 [payload] [XOR checksum] CR LF`
- GPS week rollover: chip reports week **358** instead of **2406**
- This causes the device to display ~**September 2006** as the current date

### GPS→SkyScout packets
- `@@Pb` — position/time (lat/lon in milliarcseconds)
- `@@Ou` — per-channel satellite data

### SkyScout→GPS packets
- `@@Oi` — heartbeat
- `@@Ot` — config
- `@@Oa` — start/stop

## USB

- VID: `19B4` (Celestron)
- PID: `0002`
- Type: USB Bulk Transfer
- EP_OUT: `0x03`
- EP_IN: `0x81`
- Original driver: `UsbScout.sys` / `UsbScout.inf` (on original CD)
- libusb-win32 works as replacement driver via Zadig

See [protocol.md](protocol.md) for full USB protocol documentation.

## Hidden Debug Menu

Press the **GPS button** from the main screen to access a live sensor readout:

- GPS coordinates (lat/lon)
- Elevation
- UTC time and date
- Altitude / Azimuth
- RA / Declination
- Temperature (internal sensor, °C)

## Battery Shields

The battery compartment has thin metal tube shields over the AA batteries. Missing shields cause magnetic interference with the compass sensor, resulting in GPS instability and pointing errors. Replacement shields: Celestron part CEL-SS027X (check eBay/third party suppliers).

## Antenna

The original GPS antenna is connected to the centre conductor only — the ground plane on the underside is not connected (manufacturing oversight noted by Tino, February 2026). Connecting the ground wire when reinstalling the antenna should improve GPS sensitivity.
