""" a wrapper around uasyncio.core to adapt to pyboard"""

import uasyncio_core as uac
from uasyncio_core import get_event_loop, coroutine, \
    Sleep, StopLoop, \
    async, Task # Deprecated

import pyb
import gc


#red_led = pyb.LED(1)
green_led = pyb.LED(2)
#yellow_led = pyb.LED(3)
#blue_led = pyb.LED(4)


class EventLoop(uac.EventLoop):
    _t0 = pyb.millis()

    def __init__(self):
        uac.EventLoop.__init__(self)
        self.spins = 0
        self._led = green_led
        self._led.on()

    def time(self):
        return pyb.elapsed_millis(__class__._t0) / 1000

    def wait(self, delay):
        t0 = pyb.millis()
        if delay <= 0:
            return
        ms_delay = int(delay * 1000)
        if ms_delay > 3:
            gc.collect() # we have the time, so might as well clean up
        while pyb.elapsed_millis(t0) < ms_delay:
            # If there's something useful to do we might do it here
            self.spins += 1
            if self.spins > 5000:
                self.spins = 0
                self._led.toggle()

    def run_forever(self):
        uac.EventLoop.run_forever(self)
        self._led.off()


def new_event_loop():
    return uac._event_loop_class()

def set_event_loop(loop):
    if loop is not None:
        assert isinstance(loop, EventLoop)
    uac._event_loop = loop

uac._event_loop_class = EventLoop
# Refresh the default event loop to our type
set_event_loop(None)
new_event_loop()


def sleep(secs, loop=None):
    # FIXME: deal with loop being passed
    # But sleep only happens to a coro, by the loop that runs it
    yield from uac.sleep(secs)
    

# FIXME: hack for testing
def wait(tasks, loop=None):
    loop = loop or get_event_loop()
    return tasks.pop()
