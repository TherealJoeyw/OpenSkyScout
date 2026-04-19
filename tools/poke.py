"""
SkyScout packet format experiments
Try different packet sizes and formats to find what doesn't crash it
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81
TIMEOUT_MS = 2000

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

def send_recv(dev, data, label=""):
    try:
        dev.write(EP_OUT, data, TIMEOUT_MS)
    except Exception as e:
        print(f"  {label} write error: {e}")
        return None
    try:
        resp = bytes(dev.read(EP_IN, 256, TIMEOUT_MS))
        print(f"  {label} -> {resp.hex()}")
        return resp
    except usb.core.USBError as e:
        if 'timeout' in str(e).lower():
            print(f"  {label} -> timeout (no response)")
        else:
            print(f"  {label} -> error: {e}")
        return None

dev = open_device()
print("Connected\n")

mode = sys.argv[1] if len(sys.argv) > 1 else 'size'

if mode == 'size':
    # Try different packet sizes with versionCmd (0x01)
    print("=== Testing packet sizes ===")
    for size in [1, 2, 4, 6, 8, 10, 12, 16, 20]:
        pkt = bytearray(size)
        pkt[0] = 0x01  # versionCmd in first byte
        send_recv(dev, bytes(pkt), f"size={size}")
        time.sleep(0.3)

elif mode == 'format':
    # Try 10-byte request matching response format
    print("=== Testing 10-byte request format ===")
    
    # mirror the response format: cmd in byte 0
    tests = [
        (bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), "cmd=0x01 in byte0"),
        (bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), "cmd=0x01 in byte1"),
        (bytes([0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), "cmd=0x01 in byte2"),
        (bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), "cmd=0x01 in byte3"),
        (bytes([0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]), "cmd=0x01 in byte4"),
        (bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]), "cmd=0x01 in byte5"),
        (bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00]), "cmd=0x01 in byte6"),
    ]
    for pkt, label in tests:
        send_recv(dev, pkt, label)
        time.sleep(0.3)

elif mode == 'orig':
    # Original 20-byte format, just versionCmd
    print("=== Testing original 20-byte format ===")
    hdr = bytearray(20)
    hdr[0]  = 0x00
    hdr[1]  = 0x01
    hdr[10] = 0x01  # versionCmd
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    send_recv(dev, bytes(hdr), "20-byte version")

usb.util.dispose_resources(dev)
