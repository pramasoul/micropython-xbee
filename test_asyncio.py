"""Test for micropython asyncio"""

try:
    import asyncio
    using_asyncio_spin = False
except ImportError:
    import asyncio_spin as asyncio
    using_asyncio_spin = True
    

import logging
#import sys
import unittest

import pyb

_test_EventLoop = None


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        loop = _test_EventLoop
        assert isinstance(loop, asyncio.BaseEventLoop)
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper


class CoroTestCase(unittest.TestCase):

    def setUp(self):
        logging.basicConfig(level=logging.INFO)
        global _test_EventLoop
        self.loop = asyncio.new_event_loop()
        assert self.loop is not _test_EventLoop
        _test_EventLoop = self.loop
        asyncio.set_event_loop(None)
        #assert asyncio._def_event_loop is None
        
    def tearDown(self):
        self.loop.close()
        pass

    @async_test
    def testWrap(self):
        #print(self.loop, self.loop.q)
        v = 1
        yield from asyncio.sleep(0.01, loop=self.loop)
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
        

    #@unittest.skip("sleep time accuracy in doubt")
    @async_test
    def testSleep(self):
        t0 = pyb.millis()
        yield from asyncio.sleep(0, loop=self.loop)
        self.assertIn(pyb.elapsed_millis(t0), [0,1])
        t0 = pyb.millis()
        yield from asyncio.sleep(0.012, loop=self.loop)
        self.assertTrue(12 <= pyb.elapsed_millis(t0) < 50)

    @async_test
    def testY(self):
        self.counter = 0
        for i in range(10):
            self.counter += 1
            yield
        self.assertEqual(self.counter, 10)


    def testZ(self):
        
        @asyncio.coroutine
        def fun(t):
            yield from asyncio.sleep(t, loop=self.loop)

        tasks = [asyncio.async(fun(0.01), loop=self.loop)]
        #print(self.loop, tasks)
        self.loop.run_until_complete(asyncio.wait(tasks, loop=self.loop))


    def testX(self):

        @asyncio.coroutine
        def count(n):
            for i in range(n):
                self.counter += 1
                yield

        self.counter = 0
        tasks = [
            asyncio.async(count(10), loop=self.loop),
            asyncio.async(asyncio.sleep(0.01, loop=self.loop), loop=self.loop)
        ]
        self.loop.run_until_complete(asyncio.wait(tasks, loop=self.loop))
        self.assertEqual(self.counter, 10)


    @unittest.skip("timing is unreliable except on pyboard")
    def testCreateNewTasks(self):
        self.result = ''

        @asyncio.coroutine
        def counter(name, n, naptime):
            for i in range(n):
                self.result += name
                yield from asyncio.sleep(naptime, loop=self.loop)

        @async_test
        def master():
            yield from counter('_', 3, 0.01)
            assert isinstance(_test_EventLoop, asyncio.BaseEventLoop), \
                "_test_EventLoop is %r" % _test_EventLoop
            # Start two counter tasks, slightly aharmonic so that the order of
            # their operations is deterministic. The '.' counter would run
            # a thousand times, except that the enclosing loop.run_until_complete()
            # is of this task, which returns after a short sleep
            asyncio.async(counter('|', 3, 0.19), loop=_test_EventLoop)
            asyncio.async(counter('.', 1000, 0.1), loop=_test_EventLoop)
            yield from asyncio.sleep(1, loop=self.loop)

        master()
        self.assertEqual(self.result, '___|..|..|......')
        del(self.result)


    @async_test
    def test_wait_for_A(self):
        yield from asyncio.wait_for(asyncio.sleep(0.01, loop=self.loop), None, loop=self.loop)
        yield from asyncio.wait_for(asyncio.sleep(0.02, loop=self.loop), None, loop=self.loop)

    def test_wait_for_B(self):

        @asyncio.coroutine
        def coro1():
            yield from asyncio.wait_for(asyncio.sleep(0.01, loop=self.loop), None, loop=self.loop)
            return 'foo'

        @asyncio.coroutine
        def coro2():
            v = yield from asyncio.wait_for(coro1(), None, loop=self.loop)
            self.assertEqual(v, 'foo')

        tasks = [
            asyncio.async(coro2(), loop=self.loop),
            asyncio.async(asyncio.sleep(0.02, loop=self.loop), loop=self.loop)]

        self.loop.run_until_complete(asyncio.wait(tasks, loop=self.loop))


    def test_wait_for_C(self):

        @asyncio.coroutine
        def coro1():
            self.i = 1
            yield from asyncio.wait_for(asyncio.sleep(0.01, loop=self.loop), None, loop=self.loop)
            self.i = 2
            yield from asyncio.wait_for(asyncio.sleep(0.01, loop=self.loop), None, loop=self.loop)
            self.i = 3
            return 'foo'

        @asyncio.coroutine
        def coro2():
            v = yield from asyncio.wait_for(coro1(), None, loop=self.loop)
            self.assertEqual(v, 'foo')
            self.assertEqual(self.i, 3)
            self.i = 4

        tasks = [
            asyncio.async(coro2(), loop=self.loop),
            asyncio.async(asyncio.sleep(0.02, loop=self.loop), loop=self.loop)]

        self.loop.run_until_complete(asyncio.wait(tasks, loop=self.loop))
        self.loop.close()
        self.assertEqual(self.i, 4)
        del(self.i)

    #@unittest.skip("fixme")
    def test_wait_for_D(self):
        #logging.basicConfig(level=logging.DEBUG)

        def pq(label=''):
            return
            if using_asyncio_spin:
                print(label, "q =", _test_EventLoop.q)

        @asyncio.coroutine
        def completer(ring):
            n = 0
            while True:
                for slot in range(len(ring)):
                    yield from asyncio.sleep(0.01, loop=self.loop)
                    #pyb.LED(1).toggle()
                    fut = ring[slot]
                    if fut and not fut.done():
                        fut.set_result(n)
                        pq('-')
                        n += 1

        self.i = 0
        @asyncio.coroutine
        def enter(ring):
            # A coro that enters a future into the ring
            self.i = (self.i + 1) % len(ring)
            fut = asyncio.Future(loop=self.loop)
            #self.assertIs(ring[self.i], None)
            old = ring[self.i]
            if old:
                self.assertIsInstance(old, asyncio.Future)
                self.assertTrue(old.done())
            ring[self.i] = fut
            pq('+')
            yield
            return fut
            

        @async_test
        def master():
            futures = [None] * 5
            pq('at start')
            self.completer_task = asyncio.async(completer(futures), loop=_test_EventLoop)
            pq('after starting completer task')
            for i in range(100):
                f = yield from enter(futures)
                pq('post enter')
                self.assertIsInstance(f, asyncio.Future)
                v = yield from asyncio.wait_for(f, None, loop=self.loop)
                pq('post wait_for')
                #print(v)
                self.assertEqual(v, i)

        master()
        del(self.i)

    @async_test
    def test_wait_for_timeout_A(self):
        with self.assertRaises(asyncio.TimeoutError):
            yield from asyncio.wait_for(asyncio.sleep(0.1, loop=self.loop), 0, loop=self.loop)
        yield from asyncio.wait_for(asyncio.sleep(0.1, loop=self.loop), 0.12, loop=self.loop)


    @async_test
    def test_wait_for_timeout_B(self):

        t0 = pyb.millis()
        with self.assertRaises(asyncio.TimeoutError):
            v = yield from asyncio.wait_for(asyncio.Future(loop=self.loop), 0.05, loop=self.loop)
        et = pyb.elapsed_millis(t0)


    def test_wait_for_timeout_C(self):
        
        @asyncio.coroutine
        def coro1():
            yield

        @asyncio.coroutine
        def coro2():
            yield from coro1()
            return asyncio.Future(loop=self.loop)

        @async_test
        def master():
            with self.assertRaises(asyncio.TimeoutError):
                yield from asyncio.wait_for(coro1(), 0.01, loop=self.loop)
            with self.assertRaises(asyncio.TimeoutError):
                yield from asyncio.wait_for(coro1(), 0.1, loop=self.loop)


if __name__ == '__main__':
    #logging.basicConfig(level=logging.DEBUG)
    unittest.main()
