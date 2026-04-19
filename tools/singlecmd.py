"""
OpenSkyScount - single command tool
Sends exactly ONE command and reads all responses
Usage: singlecmd.py <cmd_hex>
e.g.: singlecmd.py 38   (getOrientation)
      singlecmd.py 37   (getSensorVectors)
      singlecmd.py 35   (getTemperature)
      singlecmd.py 34   (getBatteryLevel)
Power cycle between each run
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81

cmd_byte = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x38

def wait_for_device():
    print(f"Waiting for SkyScout... (will send 0x{cmd_byte:02x})")
    while True:
        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        if dev is not None:
            try:
                if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
            except: pass
            try: dev.set_configuration()
            except: pass
            print("Connected")
            return dev
        time.sleep(0.2)

def make_packet(cmd):
    hdr = bytearray(20)
    hdr[0]  = 0x00
    hdr[1]  = 0x01
    hdr[8]  = 0
    hdr[9]  = 0
    hdr[10] = cmd
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    return bytes(hdr)

dev = wait_for_device()

# Send the single command
dev.write(EP_OUT, make_packet(cmd_byte), 5000)
print(f"Sent 0x{cmd_byte:02x}, reading responses...")

# Read everything that comes back
count = 0
while True:
    try:
        resp = bytes(dev.read(EP_IN, 256, 1000))
        count += 1
        print(f"  response {count}: {len(resp)}b {resp.hex()}")
        if len(resp) >= 10:
            w0 = struct.unpack_from('<H', resp, 0)[0]
            d0 = struct.unpack_from('<H', resp, 6)[0]
            d1 = struct.unpack_from('<H', resp, 8)[0]
            print(f"    -> w0={w0} d0={d0} d1={d1}")
    except:
        break

print(f"\nGot {count} responses")
usb.util.dispose_resources(dev)
