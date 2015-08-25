# Co-operative multitasking for the pyboard
# 

try:
    import utime as time
except ImportError:
    import time
import uheapq as heapq
import logging
import pyb
import gc


log = logging.getLogger("async")

#red_led = pyb.LED(1)
green_led = pyb.LED(2)
#yellow_led = pyb.LED(3)
blue_led = pyb.LED(4)

type_gen = type((lambda: (yield))())

class TimeoutError(Exception):
    pass

class EventLoop:
    _t0 = pyb.millis()

    def __init__(self):
        self.q = []
        self.cnt = 0
        self.idle_us = 0 # idle time in microseconds
        self.max_gc_us = 0
        self._led = green_led

    def time(self):
        return pyb.elapsed_millis(__class__._t0)

    def create_task(self, coro):
        # CPython 3.4.2
        self.call_at(0, coro)
        # CPython asyncio incompatibility: we don't return Task object

    def call_soon(self, callback, *args):
        return self.call_at(0, callback, *args)

    def call_later(self, delay, callback, *args):
        return self.call_at(self.time() + delay, callback, *args)

    def call_at(self, time, callback, *args):
        # Including self.cnt is a workaround per heapq docs
        # Returning it provides a handle for locating a queue entry
        if __debug__:
            log.debug("Scheduling %s", (time, self.cnt, callback, args))
        self.cnt += 1
        heapq.heappush(self.q, (time, self.cnt, callback, args))
        return self.cnt

    def wait(self, delay):
        t0 = pyb.millis()
        if delay == 0:
            return
        if delay == -1:
            # if delay == -1 the queue got emptied without stopping the loop
            blue_led.on()
            return
        blue_led.off()
        self._led.on()
        ust = pyb.micros()

        # Do possibly useful things in our idle time
        if delay > 6:
            gct0 = pyb.micros()
            gc.collect() # we have the time, so might as well clean up
            self.max_gc_us = max(pyb.elapsed_micros(gct0), self.max_gc_us)

        while pyb.elapsed_millis(t0) < delay:
            # Measure the idle time
            # Anything interesting at this point will require an interrupt
            # If not some pin or peripheral or user timer, then it will be
            # the 1ms system-tick interrupt, which matches our wait resolution.
            # So we can save power by waiting for interrupt.
            pyb.wfi()

        self.idle_us += pyb.elapsed_micros(ust)
        self._led.off()


    def run_forever(self):
        self.idle_us = 0
        t0_ms = pyb.millis()
        while True:
            if self.q:
                t, cnt, cb, args = heapq.heappop(self.q)
                if __debug__:
                    log.debug("Next coroutine to run: %s", (t, cnt, cb, args))
#                __main__.mem_info()
                tnow = self.time()
                delay = t - tnow
                if delay > 0:
                    self.wait(delay)
            else:
                self.wait(-1)
                # Assuming IO completion scheduled some tasks
                continue
            if callable(cb):
                cb(*args)
            else:
                delay = 0
                try:
                    if args == ():
                        args = (None,)
                    if __debug__:
                        log.debug("Coroutine %s send args: %s", cb, args)
                    ret = cb.send(*args)
                    if __debug__:
                        log.debug("Coroutine %s yield result: %s", cb, ret)
                    if isinstance(ret, SysCall):
                        arg = ret.args[0]
                        if isinstance(ret, Sleep):
                            delay = arg
                        elif isinstance(ret, IORead):
#                            self.add_reader(ret.obj.fileno(), lambda self, c, f: self.call_soon(c, f), self, cb, ret.obj)
#                            self.add_reader(ret.obj.fileno(), lambda c, f: self.call_soon(c, f), cb, ret.obj)
                            self.add_reader(arg.fileno(), lambda cb, f: self.call_soon(cb, f), cb, arg)
                            continue
                        elif isinstance(ret, IOWrite):
                            self.add_writer(arg.fileno(), lambda cb, f: self.call_soon(cb, f), cb, arg)
                            continue
                        elif isinstance(ret, IOReadDone):
                            self.remove_reader(arg.fileno())
                        elif isinstance(ret, IOWriteDone):
                            self.remove_writer(arg.fileno())

                        # EXPERIMENTAL
                        elif isinstance(ret, GetRunningCoro):
                            args = [cb]
                        elif isinstance(ret, GetRunningLoop):
                            args = [self]
                        elif isinstance(ret, BlockUntilDone):
                            if __debug__:
                                log.debug('BlockUntilDone(%s)', repr(ret.args))
                            if not hasattr(ret.args[0], 'clear_unblocking_callbacks'):
                                raise NotImplementedError("BlockUntilDone only on a future")
                            handle = None
                            # assume a Future instance
                            assert hasattr(ret.args[0], 'clear_unblocking_callbacks')
                            fut = ret.args[0]
                            if len(ret.args) > 1:
                                timeout = ret.args[1]
                                #if timeout and timeout > 0:
                                if timeout is not None:
                                    handle = self.call_later(timeout, self.future_timeout_closure(cb, fut))
                            arg.add_unblocking_callback(self.future_callback_closure(cb, handle))
                            continue
                        # end EXPERIMENTAL

                        elif isinstance(ret, StopLoop):
                            self.d_ms = pyb.elapsed_millis(t0_ms)
                            return arg
                    elif isinstance(ret, type_gen):
                        self.call_soon(ret)
                    elif ret is None:
                        # Just reschedule
                        pass
                    else:
                        assert False, "Unsupported coroutine yield value: %r (of type %r)" % (ret, type(ret))
                except StopIteration as e:
                    if __debug__:
                        log.debug("Coroutine finished: %s", cb)
                    continue
                self.call_later(delay, cb, *args)


    def run_until_complete(self, coro):
        def _run_and_stop():
            yield from coro
            yield StopLoop(0)
        self.call_soon(_run_and_stop())
        return self.run_forever()

    def unplan_call(self, h):
        # remove a call from the queue
        q = self.q
        rv = 0
        for i in range(len(q)):
            try:
                if q[i][1] is h:
                    q[i] = (0,0)
            except IndexError:
                break
        heapq.heapify(q)
        while q and q[0] == (0,0):
            heapq.heappop(q)
            rv += 1
        return rv

    def close(self):
        pass

    def future_callback_closure(self, cb, handle):
        def fcb(fut):
            if handle and handle > 0:
                self.unplan_call(handle)
                if __debug__:
                    log.debug("fcb(%r) unplan_call(%r)" % (fut, handle))
            self.call_soon(cb, fut)
        if __debug__:
            log.debug("future_callback_closure(%r, %r) returning %r" % (cb, handle, fcb))
        return fcb

    def future_timeout_closure(self, cb, fut):
        def ftc():
            fut.clear_unblocking_callbacks()
            if __debug__:
                log.debug("ftc(%r) clear_unblocking_callbacks" % fut)
            self.call_soon(cb, TimeoutError()) # FIXME
            #FIXME: ?? raise TimeoutError
        if __debug__:
            log.debug("future_timeout_closure(%r) returning %r" % (fut, ftc))
        return ftc

class SysCall:

    def __init__(self, *args):
        self.args = args

    def handle(self):
        raise NotImplementedError

class BlockUntilDone(SysCall):
    pass

class GetRunningCoro(SysCall):
    pass

class GetRunningLoop(SysCall):
    pass

class Sleep(SysCall):
    pass

class StopLoop(SysCall):
    pass

class IORead(SysCall):
    pass

class IOWrite(SysCall):
    pass

class IOReadDone(SysCall):
    pass

class IOWriteDone(SysCall):
    pass



_event_loop = None
_event_loop_class = EventLoop
def get_event_loop():
    global _event_loop
    if _event_loop is None:
        _event_loop = _event_loop_class()
    return _event_loop

def new_event_loop():
    return _event_loop_class()

def set_event_loop(loop):
    if loop is not None: # Allow None for testing correct passing of loop as kwarg
        if not isinstance(loop, EventLoop):
            raise ValueError('set_event_loop() requires an EventLoop')
    _event_loop = loop

def sleep(secs, loop=None):
    # FIXME: deal with loop being passed
    # But sleep only happens to a coro, by the loop that runs it
    yield Sleep(secs)

def coroutine(f):
    return f


# FIXME: what to do with these two?
def async(coro, loop=_event_loop):
    loop.call_soon(coro)
    # CPython asyncio incompatibility: we don't return Task object
    return coro

# CPython asyncio incompatibility: Task is a function, not a class (for efficiency)
def Task(coro, loop=_event_loop):
    # Same as async()
    loop.call_soon(coro)


# CPython asyncio incompatibility: Task is a function, not a class (for efficiency)
def Task(coro, loop=_event_loop):
    # Same as async()
    loop.call_soon(coro)



def wait_for(fut_or_coro, timeout=None, *, loop=None):
    # FIXME: deal with loop
    loop = loop or get_event_loop()

    @coroutine
    def _wait(coro, fut):
        fut.set_result((yield from coro))

    if isinstance(fut_or_coro, type_gen):
        #logging.basicConfig(level=logging.DEBUG)
        coro = fut_or_coro
        if timeout is not None:
            fut = Future()
            yield _wait(coro, fut)
            return (yield from wait_for(fut, timeout))
        return (yield from coro)

    if isinstance(fut_or_coro, Future):
        fut = fut_or_coro       # for clairity in this code

        # The slow & simple way: spin on it. Also needs timeout.
        #while not fut.done():
        #    yield
        #return fut.result()

        # The clever way, with no burn while waiting
        if not fut.done():
            v = yield BlockUntilDone(fut, timeout)
            if __debug__:
                log.debug("BlockUntilDone(%r, %r) yielded %r", fut, timeout, v)
            if isinstance(v, Exception):
                raise v
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

    def clear_unblocking_callbacks(self):
        self.ubcbs = []

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
