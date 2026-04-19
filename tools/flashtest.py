"""
OpenSkyScount - sensor data investigation
Now we know responses queue up - read immediately after each send
Power on SkyScout, wait for GPS acquiring screen, plug in USB, run script
"""
import usb.core, usb.util, struct, zlib, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_OUT     = 0x03
EP_IN      = 0x81

def wait_for_device():
    print("Waiting for SkyScout... (plug in on GPS acquiring screen)")
    while True:
        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        if dev is not None:
            try:
                if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
            except: pass
            try: dev.set_configuration()
            except: pass
            print("Connected\n")
            return dev
        time.sleep(0.2)

_seq = 0
def make_packet(cmd, payload=b''):
    global _seq
    hdr = bytearray(20)
    hdr[0]  = 0x00
    hdr[1]  = 0x01
    struct.pack_into('<I', hdr, 4, len(payload))
    hdr[8]  = _seq & 0xFF
    hdr[9]  = 0
    hdr[10] = cmd
    hdr[11] = 0
    crc = zlib.crc32(bytes(hdr[:16])) & 0xFFFFFFFF
    struct.pack_into('<I', hdr, 16, crc)
    _seq += 1
    return bytes(hdr) + payload

def send_recv(dev, cmd, payload=b'', label=''):
    dev.write(EP_OUT, make_packet(cmd, payload), 5000)
    # device sends TWO responses per command - data + ack
    responses = []
    for i in range(3):
        try:
            resp = bytes(dev.read(EP_IN, 256, 1000))
            responses.append(resp)
        except usb.core.USBError:
            break
    if responses:
        for i, r in enumerate(responses):
            print(f"  {label} r{i+1}: {len(r)}b {r.hex()}")
        return responses[0]
    print(f"  {label}: no response")
    return None

dev = wait_for_device()

print("Waiting 2 seconds for boot...")
for i in range(2, 0, -1):
    print(f"  {i}...")
    time.sleep(1)
print()

# Flush any queued responses before starting
print("Flushing pipe...")
while True:
    try:
        stale = bytes(dev.read(EP_IN, 256, 300))
        if stale:
            print(f"  flushed: {stale.hex()}")
    except:
        break
# Send all commands with immediate reads
send_recv(dev, 0x38, label='getOrientation')
time.sleep(0.5)
send_recv(dev, 0x37, label='getSensorVectors')
time.sleep(0.5)
send_recv(dev, 0x35, label='getTemperature')
time.sleep(0.5)
send_recv(dev, 0x34, label='getBatteryLevel')
time.sleep(0.5)
send_recv(dev, 0x6f, label='getDACOffset')
time.sleep(0.5)
send_recv(dev, 0x01, label='versionCmd')

print("\nDone")
usb.util.dispose_resources(dev)
