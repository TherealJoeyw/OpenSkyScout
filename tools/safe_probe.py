"""
SkyScout safe probe - only known-good commands, one per fresh connection
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81
TIMEOUT_MS = 3000

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("SkyScout not found"); sys.exit(1)
    try:
        if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
    except: pass
    try: dev.set_configuration()
    except: pass
    return dev

def make_packet(cmd, seq=0, payload=b''):
    hdr = bytearray(20)
    hdr[0] = 0x00
    hdr[1] = 0x01
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8]  = seq
    hdr[9]  = 0
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr) + payload

def send_recv(dev, cmd, seq=0, payload=b''):
    dev.write(EP_OUT, make_packet(cmd, seq, payload), TIMEOUT_MS)
    try:
        return bytes(dev.read(EP_IN, 256, TIMEOUT_MS))
    except usb.core.USBError:
        return None

# Only the commands confirmed to respond safely
SAFE_COMMANDS = [
    (0x01, 'versionCmd'),
    (0x34, 'getBatteryLevel'),
    (0x38, 'getOrientation'),
    (0x36, 'enableAutoShutdown'),
    (0x3a, 'setLED'),
    (0x6f, 'getDACOffset'),
]

if len(sys.argv) < 2:
    print("Usage: safe_probe.py <command_name>")
    print("Commands:", ', '.join(n for _,n in SAFE_COMMANDS))
    sys.exit(1)

cmd_name = sys.argv[1].lower()
cmd_byte = None
for b, n in SAFE_COMMANDS:
    if n.lower() == cmd_name or cmd_name == hex(b):
        cmd_byte = b
        break

if cmd_byte is None:
    print(f"Unknown command: {cmd_name}")
    print("Safe commands:", ', '.join(n for _,n in SAFE_COMMANDS))
    sys.exit(1)

dev = open_device()
print(f"Connected. Sending {cmd_name} (0x{cmd_byte:02x})...")

resp = send_recv(dev, cmd_byte, seq=0)
if resp:
    print(f"Response ({len(resp)} bytes): {resp.hex()}")
    # Parse fields
    if len(resp) >= 10:
        w0 = struct.unpack_from('<H', resp, 0)[0]
        w1 = struct.unpack_from('<H', resp, 2)[0]
        d0 = struct.unpack_from('<H', resp, 6)[0]
        d1 = struct.unpack_from('<H', resp, 8)[0]
        print(f"  word0={w0} ({w0:04x})  word1={w1} ({w1:04x})  data0={d0} ({d0:04x})  data1={d1} ({d1:04x})")
else:
    print("No response")

usb.util.dispose_resources(dev)
