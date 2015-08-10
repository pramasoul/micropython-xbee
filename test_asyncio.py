"""Test for micropython asyncio"""

import asyncio_spin as asyncio
#import asyncio
import logging
import unittest

import pyb

_test_event_loop = None


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        #loop = asyncio.get_event_loop()
        loop = _test_event_loop
        assert isinstance(loop, asyncio.EventLoop)
        #pyb.LED(1).on()
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper


class CoroTestCase(unittest.TestCase):

    def setUp(self):
        global _test_event_loop
        #print('(setUp', end='')
        #was_loop = asyncio._def_event_loop
        self.loop = asyncio.new_event_loop()
        _test_event_loop = self.loop
        #assert self.loop is not was_loop
        #asyncio.set_event_loop(self.loop)
        asyncio.set_event_loop(None)
        #assert asyncio._def_event_loop is self.loop
        #assert self.loop is asyncio.get_event_loop()
        #assert len(self.loop.q) == 0
        #print(')')
        
    def tearDown(self):
        pass

    @async_test
    def testWrap(self):
        #print(self.loop, self.loop.q)
        v = 1
        yield from asyncio.sleep(0.01)
        v = 2
        self.assertEqual(v, 2)

    #@unittest.skip("sleep time accuracy in doubt")
    @async_test
    def testSleep(self):
        t0 = pyb.millis()
        yield from asyncio.sleep(0)
        self.assertIn(pyb.elapsed_millis(t0), [0,1])
        t0 = pyb.millis()
        yield from asyncio.sleep(0.012)
        self.assertTrue(12 <= pyb.elapsed_millis(t0) < 50)

    @async_test
    def testY(self):
        self.counter = 0
        for i in range(10):
            #print(self.counter)
            self.counter += 1
            yield
        self.assertEqual(self.counter, 10)

    def testW(self):
        pass

    def testZ(self):
        
        @asyncio.coroutine
        def fun(t):
            yield from asyncio.sleep(t)

        tasks = [asyncio.Task(fun(0.5), loop=self.loop)]
        #print(self.loop, tasks)
        self.loop.run_until_complete(asyncio.wait(tasks, loop=self.loop))


    def testX(self):

        @asyncio.coroutine
        def count(n):
            for i in range(n):
                #print(self.counter)
                self.counter += 1
                yield

        self.counter = 0
        tasks = [
            asyncio.Task(count(10), loop=self.loop),
            asyncio.Task(asyncio.sleep(2), loop=self.loop)
        ]
        self.loop.run_until_complete(asyncio.wait(tasks))
        self.assertEqual(self.counter, 10)

if __name__ == '__main__':
    #logging.basicConfig(logging.DEBUG)
    unittest.main()
