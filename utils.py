import pyb
from pyb import Pin, SPI

class ScopePin:
    def __init__(self, pin_name):
        self.pin = Pin(pin_name, Pin.OUT_PP)
        self.pin.low()

    def pulse(self, n=1):
        for i in range(n):
            self.pin.high()
            self.pin.low()

def big_endian_int(b):
    rv = 0
    for v in list(b):
        rv = (rv << 8) + int(v)
    return rv

