"""
SkyScout pure listener - waits for device then listens
Power cycle device, then run this, then plug in
"""
import usb.core, usb.util, struct, sys, time

VENDOR_ID  = 0x19B4
PRODUCT_ID = 0x0002
EP_IN      = 0x81

def wait_for_device():
    print("Waiting for SkyScout... (plug it in)")
    while True:
        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        if dev is not None:
            try:
                if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
            except: pass
            try: dev.set_configuration()
            except: pass
            print("Connected!\n")
            return dev
        time.sleep(0.5)

dev = wait_for_device()
print("Listening for 60 seconds - press buttons and point the device around\n")

start = time.time()
count = 0
while time.time() - start < 60:
    try:
        data = bytes(dev.read(EP_IN, 4096, 1000))
        if data:
            count += 1
            t = time.time() - start
            print(f"  t={t:.2f}s chunk {count}: {len(data)}b {data.hex()}")
            if len(data) >= 10:
                w0 = struct.unpack_from('<H', data, 0)[0]
                d0 = struct.unpack_from('<H', data, 6)[0]
                d1 = struct.unpack_from('<H', data, 8)[0]
                print(f"    -> w0={w0} d0={d0} d1={d1}")
    except usb.core.USBError:
        pass

print(f"\nDone. Got {count} chunks")
usb.util.dispose_resources(dev)
