"""
SkyScout USB Tool
=================
Communicates with a Celestron SkyScout over USB using the reverse-engineered
bulk transfer protocol from SkyScout.dll (from the 2006 CD ISO).

Reverse engineering notes:
--------------------------
Header structure (20 bytes total), derived from SkyScout.dll field accessors:

  Offset  Size  Field
  0x00    1     ProtocolID      (always 0x00)
  0x01    1     ProtocolVersion (always 0x01 for version handshake)
  0x02    2     (padding/unknown)
  0x04    4     Length          (payload length, uint32 LE)
  0x08    1     Sequence        (incrementing counter)
  0x09    1     Type            (0=request, 1=response)
  0x0a    1     Command         (see command table below)
  0x0b    1     StatusCode      (0=ok in responses)
  0x0c    4     Payload ptr     (not used in wire format)
  0x10    4     CRC32           (CRC32 of header+payload)

USB pipes:
  pipe00 = write (host->device)
  pipe01 = read  (device->host)

Command bytes (from SkyScout.dll disassembly):
  0x01  versionCmd          - get firmware version
  0x15  flashCmd            - write firmware page
  0x16  getFlashCmd         - READ flash memory  <-- the one we want
  0x18  burnPageCmd         - burn page to flash
  0x32  resetCmd            - reset device
  0x33  powerdownCmd        - power down
  0x34  getBatteryLevel     - get battery level
  0x35  getTemperature      - get temperature sensor
  0x36  enableAutoShutdown  - enable/disable auto shutdown
  0x37  getSensorVectors    - get raw magnetometer/accelerometer
  0x38  getOrientation      - get computed orientation
  0x39  enableLCD           - enable/disable LCD
  0x3a  setLED              - set LED state
  0x6e  sensorCmd           - sensor command
  0x6f  getDACOffset        - get DAC offset
  0x70  setDACOffset        - set DAC offset

Requirements:
  pip install pyusb
  Windows: install UsbScout.inf driver from the original CD, or use Zadig
           to install WinUSB/libusb driver for VID=19B4 PID=0002
  Linux:   may need udev rule for VID=19B4 PID=0002

Usage:
  python skyscout.py version
  python skyscout.py battery
  python skyscout.py temperature
  python skyscout.py sensors
  python skyscout.py orientation
  python skyscout.py dump <output_file> [start_addr] [length]
  python skyscout.py reset
"""

import usb.core
import usb.util
import struct
import sys
import time
import zlib
import os

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002

# USB bulk endpoints (discovered from device descriptor)
EP_OUT = 0x03
EP_IN  = 0x81

HEADER_SIZE = 20
TIMEOUT_MS  = 5000

# Command bytes
CMD_VERSION           = 0x01
CMD_FLASH_WRITE       = 0x15
CMD_FLASH_READ        = 0x16
CMD_BURN_PAGE         = 0x18
CMD_RESET             = 0x32
CMD_POWERDOWN         = 0x33
CMD_BATTERY           = 0x34
CMD_TEMPERATURE       = 0x35
CMD_AUTO_SHUTDOWN     = 0x36
CMD_SENSOR_VECTORS    = 0x37
CMD_ORIENTATION       = 0x38
CMD_ENABLE_LCD        = 0x39
CMD_SET_LED           = 0x3a
CMD_SENSOR            = 0x6e
CMD_GET_DAC           = 0x6f
CMD_SET_DAC           = 0x70

TYPE_REQUEST  = 0
TYPE_RESPONSE = 1

_sequence = 0

def next_seq():
    global _sequence
    s = _sequence & 0xFF
    _sequence += 1
    return s


def build_header(command, payload_len=0, sequence=None, ptype=TYPE_REQUEST, status=0):
    """Build a 20-byte packet header."""
    if sequence is None:
        sequence = next_seq()
    # ProtocolID=0, ProtocolVersion=1, pad, pad, Length(4), Seq, Type, Cmd, Status, payload_ptr(4), CRC32(4)
    hdr = bytearray(HEADER_SIZE)
    hdr[0] = 0x00          # ProtocolID
    hdr[1] = 0x01          # ProtocolVersion
    hdr[2] = 0x00          # pad
    hdr[3] = 0x00          # pad
    struct.pack_into('<I', hdr, 4, payload_len)
    hdr[8]  = sequence
    hdr[9]  = ptype
    hdr[10] = command
    hdr[11] = status
    # bytes 12-15: payload pointer, not used on wire
    struct.pack_into('<I', hdr, 12, 0)
    # CRC32 over first 16 bytes (header minus CRC field itself)
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr)


def send_command(dev, command, payload=b''):
    """Send a command packet with optional payload."""
    hdr = build_header(command, len(payload))
    packet = hdr + payload
    dev.write(EP_OUT, packet, TIMEOUT_MS)


def read_response(dev):
    """Read a response header and payload. Returns (command, status, payload)."""
    # Read header
    raw = dev.read(EP_IN, 64, TIMEOUT_MS)
    print(f"  Raw response ({len(raw)} bytes): {bytes(raw).hex()}")
    if len(raw) < 4:
        raise IOError(f"Too short: got {len(raw)} bytes")

    proto_id  = raw[0]
    proto_ver = raw[1]
    length    = struct.unpack_from('<I', raw, 4)[0]
    sequence  = raw[8]
    ptype     = raw[9]
    command   = raw[10]
    status    = raw[11]
    crc_rx    = struct.unpack_from('<I', raw, 16)[0]

    # Verify CRC
    crc_calc = zlib.crc32(bytes(raw[:16])) & 0xFFFFFFFF
    if crc_rx != crc_calc:
        print(f"  [warning] CRC mismatch: got 0x{crc_rx:08x}, expected 0x{crc_calc:08x}")

    payload = b''
    if length > 0:
        payload = bytes(dev.read(EP_IN, length, TIMEOUT_MS))

    return command, status, payload


def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("ERROR: SkyScout not found. Check USB connection and driver.")
        print("  Windows: install UsbScout.inf from the original CD, or use Zadig")
        print("  Linux:   check udev rules, or run as root")
        sys.exit(1)

    # Detach kernel driver if needed (Linux)
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except (usb.core.USBError, NotImplementedError):
        pass

    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass  # May already be configured

    print(f"Connected: Celestron SkyScout (VID={VENDOR_ID:04x} PID={PRODUCT_ID:04x})")
    return dev


def cmd_version(dev):
    send_command(dev, CMD_VERSION)
    cmd, status, payload = read_response(dev)
    if status != 0:
        print(f"Version command failed: status=0x{status:02x}")
        return
    print(f"Firmware version response: {payload.hex()}")
    if len(payload) >= 2:
        print(f"  Version: {payload[0]}.{payload[1]}")


def cmd_battery(dev):
    send_command(dev, CMD_BATTERY)
    cmd, status, payload = read_response(dev)
    if status != 0:
        print(f"Battery command failed: status=0x{status:02x}")
        return
    print(f"Battery payload: {payload.hex()}")
    if len(payload) >= 2:
        level = struct.unpack_from('<H', payload, 0)[0]
        print(f"  Battery level: {level} (raw ADC)")


def cmd_temperature(dev):
    send_command(dev, CMD_TEMPERATURE)
    cmd, status, payload = read_response(dev)
    if status != 0:
        print(f"Temperature command failed: status=0x{status:02x}")
        return
    print(f"Temperature payload: {payload.hex()}")
    if len(payload) >= 2:
        val = struct.unpack_from('<H', payload, 0)[0]
        print(f"  Temperature raw: {val}")


def cmd_sensors(dev):
    send_command(dev, CMD_SENSOR_VECTORS)
    cmd, status, payload = read_response(dev)
    if status != 0:
        print(f"Sensor vectors command failed: status=0x{status:02x}")
        return
    print(f"Sensor vectors payload ({len(payload)} bytes): {payload.hex()}")
    # 3-axis mag + 3-axis accel, likely 6x int16 or 6x int32
    if len(payload) >= 12:
        vals = struct.unpack_from('<6h', payload, 0)
        print(f"  [0..5]: {vals}")
    if len(payload) >= 24:
        vals = struct.unpack_from('<6i', payload, 0)
        print(f"  As int32: {vals}")


def cmd_orientation(dev):
    send_command(dev, CMD_ORIENTATION)
    cmd, status, payload = read_response(dev)
    if status != 0:
        print(f"Orientation command failed: status=0x{status:02x}")
        return
    print(f"Orientation payload ({len(payload)} bytes): {payload.hex()}")
    if len(payload) >= 8:
        az = struct.unpack_from('<f', payload, 0)[0]
        el = struct.unpack_from('<f', payload, 4)[0]
        print(f"  Azimuth: {az:.2f}, Elevation: {el:.2f}")


def cmd_dump_flash(dev, output_file, start_addr=0x00000000, length=0x200000):
    """
    Dump flash memory using getFlashCmd (command 0x16).
    getFlashCmd takes: start_addr (uint32 LE), length (uint32 LE) as payload.
    The NAND is a Samsung K9F5608U0D: 32Mx8 = 32MB.
    Default dumps first 2MB which should contain bootloader + firmware.
    """
    PAGE_SIZE = 4096  # read in 4KB chunks

    print(f"Dumping flash: 0x{start_addr:08x} - 0x{start_addr+length:08x} -> {output_file}")
    print(f"  Total: {length // 1024}KB in {(length + PAGE_SIZE - 1) // PAGE_SIZE} pages")

    total_read = 0
    addr = start_addr

    with open(output_file, 'wb') as f:
        while total_read < length:
            chunk = min(PAGE_SIZE, length - total_read)
            payload = struct.pack('<II', addr, chunk)
            send_command(dev, CMD_FLASH_READ, payload)
            cmd, status, data = read_response(dev)

            if status != 0:
                print(f"\nERROR at 0x{addr:08x}: status=0x{status:02x}")
                break

            if len(data) == 0:
                print(f"\nERROR: empty response at 0x{addr:08x}")
                break

            f.write(data)
            total_read += len(data)
            addr += len(data)

            # Progress
            pct = total_read * 100 // length
            bar = '#' * (pct // 2) + '.' * (50 - pct // 2)
            print(f"\r  [{bar}] {pct}% ({total_read//1024}KB)", end='', flush=True)

    print(f"\nDone. {total_read} bytes written to {output_file}")


def cmd_reset(dev):
    print("Sending reset command...")
    send_command(dev, CMD_RESET)
    try:
        cmd, status, payload = read_response(dev)
        print(f"Reset response: status=0x{status:02x}")
    except Exception:
        print("Device reset (no response expected)")


def usage():
    print(__doc__)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        usage()

    command = sys.argv[1].lower()

    dev = open_device()

    if command == 'version':
        cmd_version(dev)
    elif command == 'battery':
        cmd_battery(dev)
    elif command == 'temperature':
        cmd_temperature(dev)
    elif command == 'sensors':
        cmd_sensors(dev)
    elif command == 'orientation':
        cmd_orientation(dev)
    elif command == 'reset':
        cmd_reset(dev)
    elif command == 'dump':
        out = sys.argv[2] if len(sys.argv) > 2 else 'skyscout_firmware.bin'
        start = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x00000000
        length = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x200000
        cmd_dump_flash(dev, out, start, length)
    else:
        print(f"Unknown command: {command}")
        usage()

    usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
