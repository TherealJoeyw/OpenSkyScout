# SkyScout USB Tool

Communicates with a Celestron SkyScout over USB to read sensors, dump firmware, and more.

Reverse engineered from `SkyScout.dll` (Celestron SkyScout CD, 2006).

## Setup

### Windows
1. Install the USB driver:
   - Option A: Use `UsbScout.inf` + `UsbScout.sys` from the original CD ISO
   - Option B (easier): Install [Zadig](https://zadig.akeo.ie/), select "Celestron SkyScout Device", install WinUSB driver
2. Install Python dependencies:
   ```
   pip install pyusb
   ```

### Linux
```bash
pip install pyusb
# Either run as root, or add udev rule:
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="19b4", ATTR{idProduct}=="0002", MODE="0666"' | sudo tee /etc/udev/rules.d/99-skyscout.rules
sudo udevadm control --reload-rules
```

## Usage

```bash
# Check firmware version
python skyscout.py version

# Read battery level
python skyscout.py battery

# Read temperature sensor
python skyscout.py temperature

# Read raw magnetometer + accelerometer vectors
python skyscout.py sensors

# Read computed orientation (azimuth/elevation)
python skyscout.py orientation

# Dump firmware to file (default: first 2MB)
python skyscout.py dump skyscout_firmware.bin

# Dump specific range (hex addresses)
python skyscout.py dump skyscout_firmware.bin 0x00000000 0x400000

# Reset device
python skyscout.py reset
```

## Protocol (reverse engineered from SkyScout.dll)

### Header (20 bytes)
| Offset | Size | Field           | Notes                        |
|--------|------|-----------------|------------------------------|
| 0x00   | 1    | ProtocolID      | Always 0x00                  |
| 0x01   | 1    | ProtocolVersion | Always 0x01                  |
| 0x02   | 2    | padding         |                              |
| 0x04   | 4    | Length          | Payload length, uint32 LE    |
| 0x08   | 1    | Sequence        | Incrementing counter         |
| 0x09   | 1    | Type            | 0=request, 1=response        |
| 0x0a   | 1    | Command         | See command table            |
| 0x0b   | 1    | StatusCode      | 0=OK in responses            |
| 0x0c   | 4    | (payload ptr)   | Not used on wire             |
| 0x10   | 4    | CRC32           | CRC32 of first 16 bytes      |

### Command Bytes
| Byte | Name              |
|------|-------------------|
| 0x01 | versionCmd        |
| 0x15 | flashCmd (write)  |
| 0x16 | getFlashCmd (read)|
| 0x18 | burnPageCmd       |
| 0x32 | resetCmd          |
| 0x33 | powerdownCmd      |
| 0x34 | getBatteryLevel   |
| 0x35 | getTemperature    |
| 0x36 | enableAutoShutdown|
| 0x37 | getSensorVectors  |
| 0x38 | getOrientation    |
| 0x39 | enableLCD         |
| 0x3a | setLED            |
| 0x6e | sensorCmd         |
| 0x6f | getDACOffset      |
| 0x70 | setDACOffset      |

### Hardware (from joshumax, Cloudy Nights SkyHack thread)
- CPU: Samsung S3C2410AL-20 ARM920T
- NAND: Samsung K9F5608U0D (32MB)
- RAM: Samsung K4S641632N (64MB)
- GPS: SkyLab SKG13C (SIRF, Motorola OnCore binary protocol)
- Debug UART: TP16=GND, TP17=TXD, TP18=RXD @ 9600 8N1

## Status

- [ ] Driver installation verified on Windows 10
- [ ] `version` command confirmed working
- [ ] `dump` command confirmed working
- [ ] Payload format for `sensors`/`orientation` needs verification

The `getFlashCmd` payload format (addr + length as uint32 LE) was inferred from
the disassembly of `getFlashCmd` in `SkyScout.dll`. If the dump returns errors,
the address/length encoding may need adjustment.

## Contributing

Part of the SkyScout open source revival project. See the original reverse 
engineering thread: https://www.cloudynights.com/forums/topic/471626-skyhack-things-you-shouldnt-be-doing-with-celestrons-skyscout/
