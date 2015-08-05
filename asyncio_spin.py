import time
import logging


log = logging.getLogger("asyncio")


# Workaround for not being able to subclass builtin types
class LoopStop(Exception):
    pass

class InvalidStateError(Exception):
    pass

# Object not matching any other object
_sentinel = []


class EventLoop:

    def __init__(self):
        self.q = []

    def call_soon(self, c, *args):
        self.q.append((c, args))

    def call_later(self, delay, c, *args):
        def _delayed(c, args, delay):
            yield from sleep(delay)
            self.call_soon(c, *args)
        Task(_delayed(c, args, delay))

    def run_forever(self):
        while self.q:
            c = self.q.pop(0)
            try:
                c[0](*c[1])
            except LoopStop:
                return
        # I mean, forever
        while True:
            time.sleep(1)

    def stop(self):
        def _cb():
            raise LoopStop
        self.call_soon(_cb)

    def run_until_complete(self, coro):
        t = async(coro)
        t.add_done_callback(lambda a: self.stop())
        self.run_forever()

    def close(self):
        pass


_def_event_loop = EventLoop()


class Future:

    def __init__(self, loop=_def_event_loop):
        self.loop = loop
        self.res = _sentinel
        self.cbs = []

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

    def done(self):
        return self.res is not _sentinel

    def __iter__(self):
        if self.res is _sentinel:
            yield self
        assert self.done(), "yield from wasn't used with future"
        return self.result()


class Task(Future):

    def __init__(self, coro, loop=_def_event_loop):
        super().__init__()
        self.loop = loop
        self.c = coro
        # upstream asyncio forces task to be scheduled on instantiation
        self.loop.call_soon(self)

    # like python3.4 asyncio.Task._step
    def __call__(self):
        try:
            result = next(self.c)
        except StopIteration as e:
            log.debug("Coro finished: %s", self.c)
            self.set_result(e.value)
        else:
            if isinstance(result, Future):
                # Yielded Future must come from Future.__iter__().
                result.add_done_callback(self._wakeup)
            else:
                self.loop.call_soon(self)

    def _wakeup(self, future):
        try:
            value = future.result()
        except Exception as exc:
            raise NotImplementedError("_wakeup() doesn't handle exceptions yet")
        else:
            try:
                self.c.send(value)
            except StopIteration:
                self.set_result(value)
        self = None  # Needed to break cycles when an exception occurs.


def get_event_loop():
    return _def_event_loop


# Decorator
def coroutine(f):
    return f


def ensure_future(coro):
    if isinstance(coro, Future):
        return coro
    return Task(coro)

async = ensure_future           # "Deprecated since version 3.4.4"

class _Wait(Future):

    def __init__(self, n):
        Future.__init__(self)
        self.n = n

    def _done(self):
        self.n -= 1
        log.debug("Wait: remaining tasks: %d", self.n)
        if not self.n:
            self.set_result(None)

    def __call__(self):
        pass


def wait(coro_list, loop=_def_event_loop):

    w = _Wait(len(coro_list))

    for c in coro_list:
        t = async(c)
        t.add_done_callback(lambda val: w._done())

    return w


def wait_for(fut, *args, loop=_def_event_loop):
    return (yield from fut)


import sys

if sys.platform != 'pyboard':

    def sleep(secs):
        t = time.time()
        log.debug("Started sleep at: %s, targetting: %s", t, t + secs)
        while time.time() < t + secs:
            time.sleep(0.01)
            yield
        log.debug("Finished sleeping %ss", secs)

else:

    import pyb
    #import gc
    sleepy_led = pyb.LED(2)
    sleepy_led.on()
    sleep_count = 0

    def sleep(secs):
        global sleep_count
        millis = round(secs * 1000)
        t = pyb.millis()
        log.debug("Started sleep at: %s, targeting: %s", t, t + millis)
        while pyb.elapsed_millis(t) < millis:
            #time.sleep(0.01)
            #gc.collect()
            sleep_count += 1
            if sleep_count > 1000:
                sleep_count = 0
                sleepy_led.toggle()
            yield
        log.debug("Finished sleeping %ss", secs)
