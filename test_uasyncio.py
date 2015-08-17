"""Test for micropython uasyncio for pyboard"""

from asyncio_4pyb import \
    EventLoop, new_event_loop, get_event_loop, set_event_loop, \
    coroutine, sleep, wait_for, \
    Sleep, StopLoop, GetRunningCoro, GetRunningLoop, BlockUntilDone, \
    Future, \
    TimeoutError


from asyncio_4pyb import async, Task # deprecated functions

#from heapq import heapify, heappop
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


    @async_test
    def testWrap(self):
        v = 1
        yield from sleep(0.01)
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
        self.loop.call_later(0.05, lambda: fut.set_result('happy'))
        self.assertFalse(fut.done())
        v = yield from wait_for(fut)
        self.assertTrue(fut.done())
        self.assertEqual(fut.result(), 'happy')
        self.assertEqual(v, 'happy')


    @async_test
    def testSleep(self):
        # sleep() works with acceptable timing
        @coroutine
        def ts(secs):
            t0 = pyb.millis()
            yield from sleep(secs, loop=self.loop)
            et = pyb.elapsed_millis(t0) / 1000
            self.assertTrue(secs-0.002 <= et < secs*1.01 + 0.01, \
                            "slept for %fs (expected %f)" % (et, secs))
        yield from ts(0)
        yield from ts(0.1)
        yield from ts(0.012)


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

        self.loop.run_until_complete(coro(0.01))


    def testXu(self):
        # A coroutine can count with yields and finish before a suitable sleep
        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(0.01, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testXu2(self):
        # A coroutine can loop with sleeps and get done when expected
        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield from sleep(0.001)
                yield

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(0.011, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testXu3(self):
        # A Sleep syscall works
        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield Sleep(0.001)

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(0.011, loop=self.loop))
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
            yield from counter('.', 3, 0.01)
            yield counter('1', 2, 0.01)
            self.result += 'M'
            yield counter('2', 2, 0.01)
            yield Sleep(0.05)

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
            yield counter('.', 5, 0.01) # start new task
            self.result += 'M'
            yield from counter('1', 4, 0.004) # subcoro "call", like wait_for
            self.result += 'M'
            yield Sleep(0.07)
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

        master()


    def testFib_A(self):
        # A coro can return a result calculated from other coroutines' results
        @coroutine
        def fib(n):
            yield from sleep(n/1000)
            if n <= 2:
                return 1
            return ((yield from fib(n-1)) + (yield from fib(n-2)))

        @async_test
        def master():
            result = yield from fib(10)
            self.assertEqual(result, 55)

        master()


    @async_test
    def testTimings(self):
        # Sleep timings make sense (almost)
        t0 = self.loop.time()
        t1 = self.loop.time()
        self.assertTrue(t1-t0 <= 0.001)
        t0 = self.loop.time()
        yield Sleep(0.016)
        t1 = self.loop.time()
        dt = t1 - t0
        self.assertTrue(15/1000 < 0.015) # floating point is tricky
        #FIXME self.assertTrue(15/1000 <= dt <= 17/1000, "dt %f (expected 0.016)" % dt)
        self.assertTrue(14/1000 <= dt <= 0.017, "dt %f (expected 0.016)" % dt)


    def test_wait_for_B(self):
        # coro can be waited for, and result passed back
        @coroutine
        def coro1():
            yield from wait_for(sleep(0.01, loop=self.loop), loop=self.loop)
            return 'foo'

        @coroutine
        def coro2():
            v = yield from wait_for(coro1(), None, loop=self.loop)
            self.assertEqual(v, 'foo')

        @async_test
        def master():
            yield coro2()
            yield from sleep(0.02, loop=self.loop)

        master()


    def test_wait_for_C(self):
        # coro can be waited for, and result passed back
        # They happen in correct order
        @coroutine
        def coro1():
            self.i = 1
            yield from wait_for(sleep(0.01, loop=self.loop), None, loop=self.loop)
            self.i = 2
            yield from wait_for(sleep(0.01, loop=self.loop), None, loop=self.loop)
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
            yield from sleep(0.03, loop=self.loop)

        master()
        self.assertEqual(self.i, 4)
        del(self.i)


    #@unittest.skip("wait_for() isn't ready")
    #@unittest.skip("fixme")
    def test_wait_for_D(self):
        # A coro can wait for futures
        # that another coro periodically completes
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
                    yield from sleep(0.01, loop=self.loop)
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
            yield from counter('.', 3, 0.01)
            h1 = self.loop.call_soon(counter('1', 10, 0.01))
            self.result += 'M'
            h2 = self.loop.call_later(0.03, counter('bad', 1, 0.01))
            self.assertNotEqual(h1, h2)
            yield Sleep(0.021)
            self.assertEqual(self.loop.unplan_call(h2), 1)
            self.assertEqual(self.loop.unplan_call(h1), 0)
            yield Sleep(0.015)
            self.result += 'M'

        master()
        self.assertEqual(self.result, 'M...M1111M') # no bad
        del(self.result)



    @unittest.skip("wait_for timeout on coro not implemented")
    @async_test
    def test_wait_for_timeout_A(self):
        with self.assertRaises(TimeoutError):
            yield from wait_for(sleep(0.1, loop=self.loop), 0, loop=self.loop)
        yield from wait_for(sleep(0.1, loop=self.loop), 0.12, loop=self.loop)


    @async_test
    def test_wait_for_timeout_B(self):

        t0 = pyb.millis()
        log.debug("Now %f", self.loop.time())
        with self.assertRaises(TimeoutError):
            v = yield from wait_for(Future(loop=self.loop), 0.05, loop=self.loop)
        et = pyb.elapsed_millis(t0)


    @unittest.skip("wait_for(coro) timeout not implemented")
    def test_wait_for_timeout_C(self):
        logging.basicConfig(level=logging.DEBUG)
        
        @coroutine
        def coro1():
            yield

        @coroutine
        def coro2():
            yield from coro1()
            return Future(loop=self.loop)

        @async_test
        def master():
            with self.assertRaises(TimeoutError):
                yield from wait_for(coro1(), 0.01, loop=self.loop)
            with self.assertRaises(TimeoutError):
                yield from wait_for(coro1(), 0.1, loop=self.loop)


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



if __name__ == '__main__':
    #logging.basicConfig(level=logging.DEBUG)
    unittest.main()
