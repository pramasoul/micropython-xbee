""" a wrapper around uasyncio.core to adapt to pyboard"""

import uasyncio_core as uac
from uasyncio_core import get_event_loop, coroutine, \
    Sleep, StopLoop, GetRunningCoro, GetRunningLoop, BlockUntilDone, \
    async, Task # Deprecated

import heapq
import pyb
import gc


#red_led = pyb.LED(1)
green_led = pyb.LED(2)
#yellow_led = pyb.LED(3)
blue_led = pyb.LED(4)


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
        # if delay == -1 the queue got emptied without stopping the loop
        if delay == -1:
            blue_led.on()
            return
        blue_led.off()
        if delay == 0:
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

    def unplan_call(self, h):
        q = self.q
        rv = 0
        for i in range(len(q)):
            try:
                if q[i][1] is h:
                    q[i] = (0,0)
            except IndexError:
                break
        heapq.heapify(q)
        while q[0] == (0,0):
            heapq.heappop(q)
            rv += 1
        return rv

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
    

def wait_for(fut_or_coro, timeout=None, *, loop=None):
    # FIXME: deal with timeout
    # FIXME: deal with loop

    if isinstance(fut_or_coro, uac.type_gen):
        coro = fut_or_coro
        return (yield from coro)

    if isinstance(fut_or_coro, Future):
        fut = fut_or_coro       # for clairity in this code

        # The slow & simple way: pin on it.
        #while not fut.done():
        #    yield
        #return fut.result()

        # The clever way, with no burn while waiting
        if not fut.done():
            yield BlockUntilDone(fut)
            assert fut.done()
        return (yield from fut)



################################################################
#
# Futures
# from asyncio_slow, with modifications

class InvalidStateError(Exception):
    pass

# Object not matching any other object
_sentinel = []

class Future:

    def __init__(self, loop=None):
        self.loop = loop or get_event_loop()
        self.res = _sentinel
        self.cbs = []
        self.ubcbs = []         # un-Block-ing callbacks

    def result(self):
        if self.res is _sentinel:
            raise InvalidStateError
        return self.res

    def add_done_callback(self, fn):
        if self.res is _sentinel:
            self.cbs.append(fn)
        else:
            self.loop.call_soon(fn, self)

    def set_result(self, val):
        self.res = val
        for f in self.cbs:
            f(self)
        for f in self.ubcbs:    # un-Block after the other callbacks
            f(self)

    def add_unblocking_callback(self, fn):
        if self.res is _sentinel:
            self.ubcbs.append(fn)
        else:
            # FIXME: is this correct?
            self.loop.call_soon(fn, self)

    def done(self):
        return self.res is not _sentinel

    # FIXME: is this right for uasyncio?
    def __iter__(self):
        if self.res is _sentinel:
            yield self
        assert self.done(), "yield from wasn't used with future"
        return self.result()

    def __repr__(self):
        res = self.__class__.__name__
        state =  self.res == _sentinel and 'PENDING' or 'FINISHED'
        if self.cbs:
            size = len(self.cbs)
            if size > 2:
                res += '<{}, [{}, <{} more>, {}]>'.format(
                    state, self.cbs[0],
                    size-2, self.cbs[-1])
            else:
                res += '<{}, {}>'.format(state, self.cbs)
        else:
            res += '<{}>'.format(state)
        return res


