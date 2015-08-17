try:
    import utime as time
except ImportError:
    import time
import uheapq as heapq
import logging


log = logging.getLogger("uasyncio_core")

type_gen = type((lambda: (yield))())

class TimeoutError(Exception):
    pass

class EventLoop:

    def __init__(self):
        self.q = []
        self.cnt = 0

    def time(self):
        return time.time()

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
        # Default wait implementation, to be overriden in subclasses
        # with IO scheduling
        log.debug("Sleeping for: %s", delay)
        time.sleep(delay)

    def run_forever(self):
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
                            #self.call_soon(cb, cb)
                            #continue
                            args = [cb]
                        elif isinstance(ret, GetRunningLoop):
                            #self.call_soon(cb, self)
                            #continue
                            args = [self]
                        elif isinstance(ret, BlockUntilDone):
                            # assume arg is a future
                            h = 0
                            if __debug__:
                                log.debug('BlockUntilDone(%s)', repr(ret.args))
                            handle = None
                            fut = ret.args[0]
                            if len(ret.args) > 1:
                                timeout = ret.args[1]
                                if timeout and timeout > 0:
                                    handle = self.call_later(timeout, self.future_timeout_closure(cb, fut))
                            arg.add_unblocking_callback(self.future_callback_closure(cb, handle))
                            continue
                        # end EXPERIMENTAL

                        elif isinstance(ret, StopLoop):
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
        self.run_forever()

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

def sleep(secs):
    yield Sleep(secs)

def coroutine(f):
    return f

#
# The functions below are deprecated in uasyncio, and provided only
# for compatibility with CPython asyncio
#

def async(coro, loop=_event_loop):
    loop.call_soon(coro)
    # CPython asyncio incompatibility: we don't return Task object
    return coro


# CPython asyncio incompatibility: Task is a function, not a class (for efficiency)
def Task(coro, loop=_event_loop):
    # Same as async()
    loop.call_soon(coro)
