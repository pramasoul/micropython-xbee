"""Mock standin for running Cpython"""

import time

def millis():
    return int(time.time() * 1000) & 0xffffffff

def elapsed_millis(t0):
    return (int(time.time() * 1000) - t0) & 0xffffffff

class LED:

    def __init__(self, index):
        self.index = index
        self.state = None

    def on(self):
        self.state = True

    def off(self):
        self.state = False

    def get(self):
        return self.state

    def toggle(self):
        v = self.get()
        if v:
            self.off()
        else:
            self.on()
