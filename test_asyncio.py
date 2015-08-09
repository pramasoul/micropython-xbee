"""Test for micropython asyncio"""

#import asyncio_spin as asyncio
import asyncio
import logging
import unittest

import pyb

def async_test(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        future = coro(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(future)
    return wrapper

def async_tasks(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        future = coro(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(future)
    return wrapper



class CoroTestCase(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        asyncio.set_event_loop(None)
        
    def tearDown(self):
        pass

    @async_test
    def testWrap(self):
        v = 1
        yield from asyncio.sleep(0.01, loop=self.loop)
        v = 2
        self.assertEqual(v, 2)

    #@unittest.skip("sleep time accuracy in doubt")
    @async_test
    def testSleep(self):
        t0 = pyb.millis()
        yield from asyncio.sleep(0, loop=self.loop)
        self.assertIn(pyb.elapsed_millis(t0), [0,1])
        t0 = pyb.millis()
        yield from asyncio.sleep(0.012, loop=self.loop)
        self.assertIn(pyb.elapsed_millis(t0), [12,13])

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
            yield from asyncio.sleep(t, loop=self.loop)

        tasks = [asyncio.Task(fun(0.5))]
        print(self.loop, tasks)
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
            asyncio.Task(count(10)),
            asyncio.Task(asyncio.sleep(2, loop=self.loop))
        ]
        self.loop.run_until_complete(asyncio.wait(tasks))
        self.assertEqual(self.counter, 10)

if __name__ == '__main__':
    #logging.basicConfig(logging.DEBUG)
    unittest.main()
