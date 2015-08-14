"""Test for micropython uasyncio for pyboard"""

from asyncio_4pyb import \
    EventLoop, new_event_loop, get_event_loop, set_event_loop, \
    coroutine, sleep, wait, \
    Sleep, StopLoop

from asyncio_4pyb import async, Task # deprecated functions

import logging
import unittest

import pyb

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
        #assert asyncio._def_event_loop is None
        
    def tearDown(self):
        self.loop.close()

    @async_test
    def testWrap(self):
        v = 1
        yield from sleep(0.01)
        v = 2
        self.assertEqual(v, 2)

    @unittest.skip("Future is too different from Cpython")
    def testFuture(self):
        class FooE(Exception):
            pass

        def _pfooey(f):
            raise FooE

        fut = asyncio.Future(loop=self.loop)
        self.assertFalse(fut.done())
        fut.add_done_callback(_pfooey)
        with self.assertRaises(FooE):
            fut.set_result(42)
        self.assertTrue(fut.done())
        self.assertEqual(fut.result(), 42)
        

    @unittest.skip("TODO: fix sleep")
    @async_test
    def testSleep(self):

        @coroutine
        def ts(secs):
            t0 = pyb.millis()
            yield from sleep(secs, loop=self.loop)
            et = pyb.elapsed_millis(t0) / 1000
            self.assertTrue(secs <= et < secs*1.01 + 0.01, \
                            "slept for %fs (expected %f)" % (et, secs))

        yield from ts(0)
        yield from ts(1)
        yield from ts(0.012)

    @async_test
    def testY(self):
        self.counter = 0
        for i in range(10):
            self.counter += 1
            yield
        self.assertEqual(self.counter, 10, "counter %d (expected 10)")


    def testZu(self):
        
        @coroutine
        def coro(t):
            yield from sleep(t, loop=self.loop)

        self.loop.run_until_complete(coro(0.01))


    @unittest.skip("not u")
    def testX(self):

        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield

        self.counter = 0
        tasks = [
            async(count(10), loop=self.loop),
            async(sleep(0.01, loop=self.loop), loop=self.loop)
        ]
        self.loop.run_until_complete(wait(tasks, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testXu(self):

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

        @coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield from sleep(0.001)
                yield

        self.counter = 0
        self.loop.call_soon(count(10))
        self.loop.run_until_complete(sleep(0.01, loop=self.loop))
        self.assertEqual(self.counter, 10)


    def testXu3(self):

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
            assert isinstance(_test_EventLoop, EventLoop), \
                "_test_EventLoop is %r" % _test_EventLoop
            yield counter('1', 2, 0.01)
            self.result += 'M'
            yield counter('2', 2, 0.01)
            yield Sleep(0.05)

        master()
        self.assertEqual(self.result, 'M...1M212')
        del(self.result)


    def testCreateNewTasks_B(self):
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
            assert isinstance(_test_EventLoop, EventLoop), \
                "_test_EventLoop is %r" % _test_EventLoop
            yield counter('1', 2, 0.01)
            self.result += 'M'
            self.loop.call_soon(counter('2', 2, 0.01))
            yield Sleep(0.05)

        master()
        self.assertEqual(self.result, 'M...1M212')
        del(self.result)

    def testSubCoro(self):
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

        @coroutine
        def factorial(n):
            rv = 1
            for i in range(n):
                rv *= (i+1)
                yield from sleep(0.01)
            return rv

        @async_test
        def master():
            result = yield from factorial(5)
            self.assertEqual(result, 120)

        master()


    def testFib_A(self):

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


    @unittest.skip("x")
    def test_wait_for_B(self):

        @coroutine
        def coro1():
            yield from wait_for(sleep(0.01, loop=self.loop), None, loop=self.loop)
            return 'foo'

        @coroutine
        def coro2():
            v = yield from wait_for(coro1(), None, loop=self.loop)
            self.assertEqual(v, 'foo')

        tasks = [
            async(coro2(), loop=self.loop),
            async(sleep(0.02, loop=self.loop), loop=self.loop)]

        self.loop.run_until_complete(wait(tasks, loop=self.loop))


    @unittest.skip("x")
    def test_wait_for_C(self):

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

        tasks = [
            async(coro2(), loop=self.loop),
            async(sleep(0.02, loop=self.loop), loop=self.loop)]

        self.loop.run_until_complete(wait(tasks, loop=self.loop))
        self.loop.close()
        self.assertEqual(self.i, 4)
        del(self.i)

    @unittest.skip("x")
    #@unittest.skip("fixme")
    def test_wait_for_D(self):
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
            yield
            return fut
            

        @async_test
        def master():
            futures = [None] * 5
            pq('at start')
            self.completer_task = async(completer(futures), loop=_test_EventLoop)
            pq('after starting completer task')
            for i in range(100):
                f = yield from enter(futures)
                pq('post enter')
                self.assertIsInstance(f, Future)
                v = yield from wait_for(f, None, loop=self.loop)
                pq('post wait_for')
                #print(v)
                self.assertEqual(v, i)

        master()
        del(self.i)

    @unittest.skip("x")
    @async_test
    def test_wait_for_timeout_A(self):
        with self.assertRaises(TimeoutError):
            yield from wait_for(sleep(0.1, loop=self.loop), 0, loop=self.loop)
        yield from wait_for(sleep(0.1, loop=self.loop), 0.12, loop=self.loop)


    @unittest.skip("x")
    @async_test
    def test_wait_for_timeout_B(self):

        t0 = pyb.millis()
        with self.assertRaises(TimeoutError):
            v = yield from wait_for(Future(loop=self.loop), 0.05, loop=self.loop)
        et = pyb.elapsed_millis(t0)


    @unittest.skip("x")
    def test_wait_for_timeout_C(self):
        
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


if __name__ == '__main__':
    #logging.basicConfig(level=logging.DEBUG)
    unittest.main()
