"""Test for micropython uasyncio for pyboard"""

from async_pyb import \
    EventLoop, new_event_loop, get_event_loop, set_event_loop, \
    coroutine, async, sleep, wait_for, \
    Sleep, StopLoop, GetRunningCoro, GetRunningLoop, BlockUntilDone, \
    Future, \
    TimeoutError


from async_pyb import async, Task # deprecated functions

#from heapq import heapify, heappop
import gc
import logging
import unittest

import pyb

log = logging.getLogger("test")

_test_EventLoop = None


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = coroutine(f)
        loop = _test_EventLoop
        assert isinstance(loop, EventLoop)
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper


class CoroTestCase(unittest.TestCase):

    def setUp(self):
        logging.basicConfig(level=logging.INFO)
        global _test_EventLoop
        self.loop = new_event_loop()
        assert self.loop is not _test_EventLoop
        _test_EventLoop = self.loop
        set_event_loop(None)
        
    def tearDown(self):
        self.loop.close()
        gc.collect()

    @async_test
    def testWrap(self):
        v = 1
        yield from sleep(10)
        v = 2
        self.assertEqual(v, 2)


    @async_test
    def testGetRunningCoro(self):
        v = yield GetRunningCoro(None)
        self.assertTrue(repr(v).startswith("<generator object '_run_and_stop'"))

    @async_test
    def testGetRunningLoop(self):
        v = yield GetRunningLoop(None)
        self.assertIs(v, self.loop)


    def testFuture_A(self):
        # A future, when done, runs callbacks and has a result
        class FooE(Exception):
            pass

        def _pfooey(f):
            raise FooE

        fut = Future(loop=self.loop)
        self.assertFalse(fut.done())
        fut.add_done_callback(_pfooey)
        with self.assertRaises(FooE):
            fut.set_result(42)
        self.assertTrue(fut.done())
        self.assertEqual(fut.result(), 42)
        

    @async_test
    def testFuture_B(self):
        # If a future is done, a yield from it returns its result
        fut = Future(loop=self.loop)
        fut.set_result('happy')
        v = yield from fut
        self.assertEqual(v, 'happy')
        


    @async_test
    def testwaitForFuture_A(self):
        # If a future is done, a wait_for() of it returns its result
        fut = Future(loop=self.loop)
        fut.set_result('happy')
        v = yield from wait_for(fut)
        #print("yield from wait_for(future) returned", v)
        self.assertEqual(fut.result(), 'happy')
        self.assertEqual(v, 'happy')
        

    @async_test
    def testWaitForFuture_C(self):
        # If a future is not done, a wait_for() of it waits for its
        # result and returns it
        fut = Future(loop=self.loop)
        self.loop.call_later(50, lambda: fut.set_result('happy'))
        self.assertFalse(fut.done())
        v = yield from wait_for(fut)
        self.assertTrue(fut.done())
        self.assertEqual(fut.result(), 'happy')
        self.assertEqual(v, 'happy')


    def testWaitForFutureMultipleWaitersSuccess(self):
        # Multiple coros can wait on a Future that is fulfilled
        self.returns = []

        @coroutine
        def waiter(f, name):
            yield from wait_for(f)
            self.returns.append(name)

        @coroutine
        def master():
            fut = Future()
            yield waiter(fut, 'foo')
            yield waiter(fut, 'bar')
            fut.set_result(None)
            yield from sleep(1)

        loop = self.loop
        loop.run_until_complete(master())
        #self.assertEqual(', '.join(self.returns), 'foo, bar')
        self.assertEqual(set(self.returns), set(['foo', 'bar']))

    def testWaitForFutureMultipleWaitersTimeout(self):
        # Multiple coros can wait on a Future that is not fulfilled,
        # timing out
        self.returns = []

        @coroutine
        def waiter(f, name, patience):
            try:
                yield from wait_for(f, patience)
            except TimeoutError:
                self.returns.append(name + ' Timeout @%d' % patience)
            else:
                self.returns.append(name + ' got it')

        @coroutine
        def master():
            fut = Future()
            yield waiter(fut, 'foo', 10)
            yield waiter(fut, 'bar', 12)
            self.assertEqual(self.returns, [])
            yield from sleep(15)

        loop = self.loop
        loop.run_until_complete(master())
        self.assertEqual(', '.join(self.returns), 'foo Timeout @10, bar Timeout @12')


    def testWaitForFutureMultipleWaitersSomeTimeout(self):
        # Multiple coros can wait on a Future, that is fulfilled after
        # some time out and before others
        self.returns = []

        @coroutine
        def waiter(f, name, patience):
            try:
                yield from wait_for(f, patience)
            except TimeoutError:
                self.returns.append(name + ' Timeout @%d' % patience)
            else:
                self.returns.append(name + ' got it')

        @coroutine
        def master():
            fut = Future()
            yield waiter(fut, 'foo', 10)
            yield waiter(fut, 'bar', 20)
            self.assertEqual(self.returns, [])
            yield from sleep(12)
            fut.set_result(None)
            yield from sleep(5)

        loop = self.loop
        loop.run_until_complete(master())
        self.assertEqual(', '.join(self.returns), 'foo Timeout @10, bar got it')


    @async_test
    def testSleep(self):
        # sleep() works with acceptable timing
        @coroutine
        def ts(ms):
            t0 = pyb.millis()
            yield from sleep(ms, loop=self.loop)
            et = pyb.elapsed_millis(t0)
            self.assertTrue(ms <= et <= ms+2, \
                            "slept for %ds (expected %d)" % (et, ms))
        yield from ts(0)
        yield from ts(1)
        yield from ts(12)


    @async_test
    def testY(self):
        # A plain yield in a loop is allowed
        self.counter = 0
        for i in range(10):
            self.counter += 1
            yield
        self.assertEqual(self.counter, 10, "counter %d (expected 10)")


    def testZu(self):
        # A coroutine can sleep
        @coroutine
        def coro(t):
            yield from sleep(t, loop=self.loop)

        self.loop.run_until_complete(coro(10))


    def testXu(self):
        # A coroutine can count with yields and finish before a suitable sleep
        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(10, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testXu2(self):
        # A coroutine can loop with sleeps and get done when expected
        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield from sleep(1)
                yield

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(11, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testXu3(self):
        # A Sleep syscall works
        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield Sleep(1)

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(11, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testCreateNewTasks_A(self):
        # A "yield from" is a coro's version of a subroutine call
        # A coro can start other coroutines by yield'ing them
        # Multiple coros can run and sleep in the expected order
        self.result = ''

        @coroutine
        def counter(name, n, naptime):
            for i in range(n):
                self.result += name
                yield Sleep(naptime)

        @async_test
        def master():
            self.result += 'M'
            yield from counter('.', 3, 10)
            yield counter('1', 2, 10)
            self.result += 'M'
            yield counter('2', 2, 10)
            yield Sleep(50)

        master()
        self.assertEqual(self.result, 'M...1M212')
        del(self.result)


    def testSubCoro(self):
        # A "yield from" is a coro's version of a subroutine call
        # A coro can start other coroutines by yield'ing them
        # Multiple coros can run and sleep in the expected order
        self.result = ''

        @coroutine
        def counter(name, n, naptime):
            for i in range(n):
                self.result += name
                yield Sleep(naptime)

        @async_test
        def master():
            self.result += 'M'
            yield counter('.', 5, 10) # start new task
            self.result += 'M'
            yield from counter('1', 4, 4) # subcoro "call", like wait_for
            self.result += 'M'
            yield Sleep(75)
            self.result += 'E'

        master()
        self.assertEqual(self.result, 'M.M111.1M...E')
        del(self.result)


    def testSubCoroWithRV(self):
        # A coro can return a result
        @coroutine
        def factorial(n):
            rv = 1
            for i in range(n):
                rv *= (i+1)
                yield
            return rv

        @async_test
        def master():
            result = yield from factorial(5)
            self.assertEqual(result, 120)


    def testFib_A(self):
        # A coro can return a result calculated from other coroutines' results
        @coroutine
        def fib(n):
            yield from sleep(n)
            if n <= 2:
                return 1
            return ((yield from fib(n-1)) + (yield from fib(n-2)))

        @async_test
        def master():
            result = yield from fib(10)
            self.assertEqual(result, 55)



    @async_test
    def testTimings(self):
        # Sleep timings make sense (almost)
        t0 = self.loop.time()
        t1 = self.loop.time()
        self.assertTrue(t1-t0 <= 1)
        t0 = self.loop.time()
        yield Sleep(16)
        t1 = self.loop.time()
        dt = t1 - t0
        self.assertTrue(14 <= dt <= 17, "dt %f (expected 16ms)" % dt)


    def test_wait_for_B(self):
        # coro can be waited for, and result passed back
        @coroutine
        def coro1():
            yield from wait_for(sleep(10, loop=self.loop), loop=self.loop)
            return 'foo'

        @coroutine
        def coro2():
            v = yield from wait_for(coro1(), None, loop=self.loop)
            self.assertEqual(v, 'foo')

        @async_test
        def master():
            yield coro2()
            yield from sleep(20, loop=self.loop)

        master()


    def test_wait_for_C(self):
        # coro can be waited for, and result passed back
        # They happen in correct order
        @coroutine
        def coro1():
            self.i = 1
            yield from wait_for(sleep(10, loop=self.loop), None, loop=self.loop)
            self.i = 2
            yield from wait_for(sleep(10, loop=self.loop), None, loop=self.loop)
            self.i = 3
            return 'foo'

        @coroutine
        def coro2():
            v = yield from wait_for(coro1(), None, loop=self.loop)
            self.assertEqual(v, 'foo')
            self.assertEqual(self.i, 3)
            self.i = 4

        @async_test
        def master():
            yield coro2()
            yield from sleep(30, loop=self.loop)

        master()
        self.assertEqual(self.i, 4)
        del(self.i)


    def test_wait_for_D(self):
        # A coro can wait for futures that another coro periodically completes
        #logging.basicConfig(level=logging.DEBUG)

        def pq(label=''):
            return
            if using_asyncio_spin:
                print(label, "q =", _test_EventLoop.q)

        @coroutine
        def completer(ring):
            n = 0
            while True:
                for slot in range(len(ring)):
                    yield from sleep(10, loop=self.loop)
                    #pyb.LED(1).toggle()
                    fut = ring[slot]
                    if fut and not fut.done():
                        fut.set_result(n)
                        pq('-')
                        n += 1

        self.i = 0
        @coroutine
        def enter(ring):
            # A coro that enters a future into the ring
            self.i = (self.i + 1) % len(ring)
            fut = Future(loop=self.loop)
            #self.assertIs(ring[self.i], None)
            old = ring[self.i]
            if old:
                self.assertIsInstance(old, Future)
                self.assertTrue(old.done())
            ring[self.i] = fut
            pq('+')
            yield               # merely to make it a coro
            return fut
            

        @async_test
        def master():
            futures = [None] * 5
            pq('at start')
            self.completer_task = async(completer(futures), loop=_test_EventLoop)
            pq('after starting completer task')
            for i in range(20):
                f = yield from enter(futures)
                pq('post enter')
                self.assertIsInstance(f, Future)
                v = yield from wait_for(f, None, loop=self.loop)
                pq('post wait_for')
                #print(v)
                self.assertEqual(v, i)

        master()
        del(self.i)


    def testRemoveQueuedCallback(self):
        # loop.call_*() returns unique (for that loop) handle
        # a not-yet-called queued call can be unplanned with unplan_call()
        # unplan_call() returns a count of the number of planned calls elided
        self.result = ''

        @coroutine
        def counter(name, n, naptime):
            for i in range(n):
                self.result += name
                yield Sleep(naptime)

        @async_test
        def master():
            self.result += 'M'
            yield from counter('.', 3, 10)
            h1 = self.loop.call_soon(counter('1', 10, 10))
            self.result += 'M'
            h2 = self.loop.call_later(30, counter('bad', 1, 10))
            self.assertNotEqual(h1, h2)
            yield Sleep(21)
            self.assertEqual(self.loop.unplan_call(h2), 1)
            self.assertEqual(self.loop.unplan_call(h1), 0)
            yield Sleep(15)
            self.result += 'M'

        master()
        self.assertEqual(self.result, 'M...M1111M') # no bad
        del(self.result)



    @unittest.skip("broken test, conceptually flawed")
    def testBlockUntilDone(self):
        # BlockUntilDone SysCall works as demonstrated

        @coroutine
        def waitToReturn(duration, statement, fut):
            yield from sleep(duration)
            fut.set_result(statement)

        @async_test
        def master():
            fut = Future()
            co = waitToReturn(10, 'cows', fut)
            v_co = yield co
            v_bud = yield BlockUntilDone(co, None)
            self.assertEqual(v_bud, 'cows')

        master()
        

    @async_test
    def testWaitForCoroutine(self):
        with self.assertRaises(TimeoutError):
            yield from wait_for(sleep(100, loop=self.loop), 1, loop=self.loop)
        with self.assertRaises(TimeoutError):
            yield from wait_for(sleep(100, loop=self.loop), 0, loop=self.loop)

        yield from wait_for(sleep(10, loop=self.loop), 10, loop=self.loop)

        # Note there's a little grace period for the timeout:
        # (But not much when __debug__ is False)
        #yield from wait_for(sleep(10, loop=self.loop), 9, loop=self.loop)
        #yield from wait_for(sleep(10, loop=self.loop), 8, loop=self.loop)
        with self.assertRaises(TimeoutError):
            yield from wait_for(sleep(10, loop=self.loop), 7, loop=self.loop)
        return


    @async_test
    def testWaitForFutureTimeout(self):
        t0 = pyb.millis()
        with self.assertRaises(TimeoutError):
            v = yield from wait_for(Future(loop=self.loop), 50, loop=self.loop)
        et = pyb.elapsed_millis(t0)
        self.assertTrue(49 <= et < 55, 'et was %rms (expected 50ms)' % et)


    def testWFC(self):

        @coroutine
        def w(coro, fut):
            v = yield from coro
            fut.set_result(v)
            return v

        @coroutine
        def x(duration, statement):
            yield from sleep(duration)
            return statement

        @async_test
        def master():
            fut = Future()
            self.assertEqual((yield from x(10, 'happy')), 'happy')
            self.assertEqual((yield from w(x(10, 'pleased'), fut)), 'pleased')
            self.assertEqual(fut.result(), 'pleased')
            #logging.basicConfig(level=logging.DEBUG)
            #log.debug("Now %f", self.loop.time())

            # One that completes before the timeout
            t0 = pyb.millis()
            fut = Future()
            self.loop.call_soon(w(x(20, 'good'), fut))
            v = yield from wait_for(fut, 50)
            self.assertEqual(v, 'good')
            et = pyb.elapsed_millis(t0)
            self.assertTrue(20 <= et < 25, 'et was %rms (expected 20-25ms)' % et)
            
            # One that hits the timeout
            t0 = pyb.millis()
            fut = Future()
            self.loop.call_soon(w(x(20, 'fine'), fut))
            with self.assertRaises(TimeoutError):
                v = yield from wait_for(fut, 10)
            et = pyb.elapsed_millis(t0)            
            self.assertTrue(10 <= et < 15, 'et was %rms (expected 10-15ms)' % et)

        master()


    def testMessWithGetRunningCoro(self):

        @coroutine
        def coro(me, duration):
            yield Sleep(duration)
            self.loop.call_soon(me, 'coro-scheduled')
            #print('coro returning')
            return 'from coro'

        @async_test
        def master():
            t0 = pyb.millis()
            fut = Future()
            me = yield GetRunningCoro(None)
            self.assertEqual(self.loop.q, []) # nobody in the queue
            yield from sleep(1)
            self.assertEqual(self.loop.q, []) # nobody in the queue
            v_coro = yield coro(me, 10) # starts
            self.assertEqual(len(self.loop.q), 1) # coro is queued
            v_sleep = yield Sleep(20)
            et = pyb.elapsed_millis(t0)            
            # We got send()'ed to when the coro finished, before the Sleep
            self.assertTrue(10 <= et < 15, 'et was %rms' % et)
            self.assertEqual(v_sleep, 'coro-scheduled')

            # But we have an extra call to us in the queue, left over from our yield coro
            #Fails: self.assertEqual(self.loop.q, []) # nobody in the queue
            #print("loop.q is", self.loop.q)

            #print("v_coro = %r, v_sleep = %r" % (v_coro, v_sleep))
            #print("Another yield returns", (yield))
            #print("A Sleep(25) yield returns", (yield Sleep(25)))
            #print("Another yield returns", (yield))
            
        master()


    def testIdleAndTotalTimes(self):

        @coroutine
        def coro(spins, count, nap):
            t = 0
            for i in range(count):
                for j in range(spins):
                    t += j
                yield from sleep(nap)
            return t

        loop = self.loop
        loop.run_until_complete(coro(1, 10, 1))
        idle_frac = loop.idle_us / (loop.d_ms * 1000)
        self.assertTrue(idle_frac > 0.3)
        print("%dms, %dus idle, (%f)" % (loop.d_ms, loop.idle_us, idle_frac))
        loop.run_until_complete(coro(1, 10, 10))
        idle_frac = loop.idle_us / (loop.d_ms * 1000)
        self.assertTrue(idle_frac > 0.9)
        print("%dms, %dus idle, (%f)" % (loop.d_ms, loop.idle_us, idle_frac))
        loop.run_until_complete(coro(1, 1, 50))
        idle_frac = loop.idle_us / (loop.d_ms * 1000)
        self.assertTrue(idle_frac > 0.95)
        print("%dms, %dus idle, (%f)" % (loop.d_ms, loop.idle_us, idle_frac))


    def testYieldFromPassthru(self):
        # How to pass through a 'yield from'

        def ranger(n):
            v = 0
            for i in range(n):
                v += i
                yield i
            return v
        
        def retRightAway(v):
            for x in []:
                yield x
            return v

        def delranger(n):
            return (yield from ranger(n))

        def delany(g):
            # Delegate to any generator
            return (yield from g)

        def yar(gen):
            # Capture yields and return value
            yields = []
            while True:
                try:
                    yields.append(gen.send(None))
                except StopIteration as e:
                    return (yields, e.value)

        self.assertEqual(list(range(3)), [0,1,2])
        self.assertEqual(list(v for v in range(3)), [0,1,2])
        self.assertEqual(list(v for v in ranger(3)), [0,1,2])
        self.assertEqual(list(v for v in delranger(3)), [0,1,2])
        self.assertEqual(yar(ranger(3)), ([0,1,2], 3))
        self.assertEqual(yar(delranger(3)), ([0,1,2], 3))
        self.assertEqual(yar(delany(ranger(3))), ([0,1,2], 3))
        self.assertEqual(yar(ranger(0)), ([], 0))
        self.assertEqual( (yield from retRightAway(7)) , 7)
        self.assertEqual(delany(retRightAway(7)), 7)
        self.assertEqual(yar(delany(retRightAway(7))), ([], 7))


    @unittest.skip("takes 20 seconds")
    def testStressFib(self):
        # Stress test
        @coroutine
        def fib(n):
            #yield from sleep(n)
            if n <= 2:
                return 1
            return ((yield from fib(n-1)) + (yield from fib(n-2)))

        @coroutine
        def master():
            result = yield from fib(25)
            self.assertEqual(result, 75025)

        loop = self.loop
        loop.run_until_complete(master())
        idle_frac = loop.idle_us / (loop.d_ms * 1000)
        #self.assertTrue(idle_frac > 0)
        print("%dms, %dus idle, (%f)" % (loop.d_ms, loop.idle_us, idle_frac))


    def testStressSharksAndMinnows(self):

        self.minnows = set()
        self.n_sharks = 0

        @coroutine
        def minnow(t):
            minnows = self.minnows
            fut = Future()
            minnows.add(fut)
            while True:
                try:
                    yield from wait_for(fut, pyb.rng() % t)
                    return
                except TimeoutError:
                    if len(minnows) < 32:
                        yield minnow(t) # Create another
            
        @coroutine
        def shark(t, n):
            self.n_sharks += 1
            belly = n
            while belly > 0:
                yield from sleep(t)
                # If well-fed, reproduce
                if belly > 2*n:
                    yield shark(t, n)
                    belly -= n
                # Try to bite a minnow
                if len(self.minnows) > pyb.rng() & 0x1f:
                    f = self.minnows.pop()
                    f.set_result(None)
                    belly += 2
                else:
                    belly -= 1
            # Starved. Die.
            self.n_sharks -= 1

        @coroutine
        def master():
            for i in range(8):
                yield minnow(200)
                yield from sleep(10)
            for i in range(3):
                yield shark(20, 5)
                yield from sleep(7)
            minnows = self.minnows
            print('')
            while True:
                print("\r%d minnows and %d sharks       " \
                      % (len(minnows), self.n_sharks), end='')
                if not (len(minnows) and self.n_sharks):
                    break
                yield from sleep(50)
                yield minnow(100)

        loop = self.loop
        loop.run_until_complete(master())
        idle_frac = loop.idle_us / (loop.d_ms * 1000)
        #self.assertTrue(idle_frac > 0)
        print("\n%dms, %dus idle, (%f)" % (loop.d_ms, loop.idle_us, idle_frac))
        print("Max gc time %dus" % self.loop.max_gc_us)
        del self.minnows
        del self.n_sharks
        

def main():
    while True:
        unittest.main()

if __name__ == '__main__':
    #logging.basicConfig(level=logging.DEBUG)
    main()
