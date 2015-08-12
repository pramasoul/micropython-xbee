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


class BaseEventLoop:
    pass

class EventLoop(BaseEventLoop):

    def __init__(self, verbose=False):
        self.q = []
        self.verbose = verbose

    def call_soon(self, c, *args):
        self.q.append((c, args))

    def call_later(self, delay, c, *args):
        def _delayed(c, args, delay):
            yield from sleep(delay)
            self.call_soon(c, *args)
        Task(_delayed(c, args, delay))

    def run_forever(self):
        #leds_off()
        n = 0
        while self.q:
            toggle_yellow()
            if self.verbose and n % 1000 == 0:
                toggle_red()
                log.debug("r_f %r: %dk q=%r" % (self, n/1000, self.q))
            n += 1
            c = self.q.pop(0)
            try:
                c[0](*c[1])
            except LoopStop:
                yellow_off()
                return
        raise RuntimeError("run_forever() ran out of queue!") # DEBUG
        # I mean, forever
        while True:
            # Make visible that we've fallen into this pit
            toggle_blue()
            time.sleep(1)

    def stop(self):
        def _cb():
            raise LoopStop
        self.call_soon(_cb)

    def run_until_complete(self, coro):
        t = async(coro, loop=self)
        t.add_done_callback(lambda a: self.stop())
        #print("r_u_c: t=%r, q=%r" % (t, self.q))     # DEBUG
        self.run_forever()

    def close(self):
        pass


_def_event_loop = EventLoop()

def new_event_loop():
    return EventLoop()

def get_event_loop():
    return _def_event_loop

def set_event_loop(loop):
    global _def_event_loop
    _def_event_loop = loop


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



class Task(Future):

    def __init__(self, coro, loop=None):
        super().__init__()
        self.loop = loop or _def_event_loop
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

    def __repr__(self):
        res = super().__repr__()
        i = res.find('<')
        if i < 0:
            i = len(res)
        res = res[:i] + '(<{}>)'.format(str(self.c)) + res[i:]
        return res



# Decorator
def coroutine(f):
    return f


def ensure_future(coro_or_future, loop=None):
    if isinstance(coro_or_future, Future):
        return coro_or_future
    return Task(coro_or_future, loop=loop)

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
    # https://docs.python.org/3/library/asyncio-task.html
    # This function is a coroutine, usage:
    #   "result = yield from asyncio.wait_for(fut, 60.0)"
    #
    # This almost works:
    #return (yield from fut)
    # but not quite. Brute-force it for now:
    if isinstance(fut, Future):
        while not fut.done():
            yield
        return fut.result()
    else:
        return (yield from fut)

import sys

if sys.platform == 'pyboard':

    import pyb
    #import gc
    red_led = pyb.LED(1)
    green_led = pyb.LED(2)
    yellow_led = pyb.LED(3)
    blue_led = pyb.LED(4)

    sleepy_led = green_led
    sleepy_led.on()
    sleep_count = 0

    def sleep(secs, loop=None):
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

    def leds_off():
        for i in range(4):
            pyb.LED(i+1).off()

    def toggle_yellow():
        yellow_led.toggle()

    def toggle_blue():
        blue_led.toggle()

    def toggle_red():
        red_led.toggle()

    def yellow_off():
        yellow_led.off()
else:

    def sleep(secs, loop=None):
        t = time.time()
        log.debug("Started sleep at: %s, targetting: %s", t, t + secs)
        while time.time() < t + secs:
            time.sleep(0.01)
            yield
        log.debug("Finished sleeping %ss", secs)

    def toggle_yellow():
        pass

    def toggle_blue():
        pass

    def toggle_red():
        pass

    def yellow_off():
        pass

    def leds_off():
        pass
