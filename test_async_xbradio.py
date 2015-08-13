"""Test for asyncio-based XBee Pro S3B library"""

import asyncio_spin as asyncio
import logging
import unittest
import pyb

#from ubinascii import hexlify

from async_xbradio import XBRadio, \
    FrameOverrunError, FrameWaitTimeout


from pyb import SPI, Pin, info, millis, elapsed_millis, micros, elapsed_micros


_test_EventLoop = None

def async_test(f):
    def wrapper(*args, **kwargs):
        global _test_EventLoop
        coro = asyncio.coroutine(f)
        #loop = asyncio.get_event_loop()
        loop = _test_EventLoop
        #print("wrapper loop %r" % loop)
        assert isinstance(loop, asyncio.EventLoop)
        #pyb.LED(1).on()
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper


class CoroTestCase(unittest.TestCase):

    def setUp(self):
        global _test_EventLoop
        #print('(setUp', end='')
        #was_loop = asyncio._def_event_loop
        self.loop = asyncio.new_event_loop()
        _test_EventLoop = self.loop
        #assert self.loop is not was_loop

        #XBRadio uses default loop:
        asyncio.set_event_loop(self.loop)
        #asyncio.set_event_loop(None)


        #assert asyncio._def_event_loop is self.loop
        #assert self.loop is asyncio.get_event_loop()
        #assert len(self.loop.q) == 0
        #print(')')

    def tearDown(self):
        pass

    @async_test
    def testWrap(self):
        v = 1
        yield from asyncio.sleep(0.1)
        v = 2
        self.assertEqual(v, 2)


class RadioTestCase(unittest.TestCase):

    def setUp(self):
        global _test_EventLoop
        logging.basicConfig(logging.INFO)
        self.loop = asyncio.new_event_loop()
        _test_EventLoop = self.loop
        # XBRadio assumes default loop, so set here
        asyncio.set_event_loop(self.loop)
        #self.xb = create_test_radio('gse')
        self.xb = create_test_radio('flt')
        
    def tearDown(self):
        pass

    def testIsRadio(self):
        self.assertIsInstance(self.xb, XBRadio)

    @async_test
    def testSleep(self):
        yield from asyncio.sleep(0.01)

    @async_test
    def testStartRadio(self):
        #logging.basicConfig(logging.DEBUG)
        #self.loop.verbose = True
        #self.xb.verbose = True
        #self.xb.xcvr.verbose = True
        yield from self.xb.start()
        #pyb.LED(1).on()
        self.assertTrue(self.xb.started)

    @async_test
    def testAddress(self):
        #self.xb.verbose = True
        #self.xb.xcvr.verbose = True
        #print("pre-start: ", self.loop, self.loop.q)
        #logging.basicConfig(logging.DEBUG)
        yield from self.xb.start()
        self.assertIsInstance(self.xb.address, bytes)
        self.assertNotEqual(sum(self.xb.address), 0)
        #print(self.loop, self.loop.q)

    @async_test
    def testATcmds(self):
        xb = self.xb
        yield from xb.start()
        at = xb.send_AT_cmd
        yield from at('TP')
        yield from at('%V')
        yield from asyncio.sleep(0.01)
        self.assertTrue(1 < xb.values['TP'] < 60, "bad temperature %d" % xb.values['TP'])
        self.assertTrue(3200 < xb.values['%V'] < 3400, "bad voltage %d" % xb.values['%V'])
        
    @unittest.skip("incomplete")
    @async_test
    def testRxErrorCount(self):
        xb = self.xb
        yield from xb.start()
        at = xb.send_AT_cmd
        yield from at('ER')

    @async_test
    def testGetFrameTimeout(self):
        xb = self.xb
        yield from xb.start()
        with self.assertRaises(FrameWaitTimeout):
            yield from xb.xcvr.get_frame(0)
        t0 = millis()
        with self.assertRaises(FrameWaitTimeout):
            yield from xb.xcvr.get_frame(34)
        et = elapsed_millis(t0)
        self.assertTrue(34 <= et < 38, "took %dms (expected 34ms)" % et)


    @async_test
    def testSendToSelf(self):
        xb = self.xb
        yield from xb.start()
        self.assertEqual(xb.rx_available(), 0)
        yield from xb.tx('foo', xb.address)
        yield from asyncio.sleep(0.01)
        self.assertEqual(xb.rx_available(), 1)
        yield from xb.tx('bar', xb.address)
        yield from asyncio.sleep(0.1)
        self.assertEqual(xb.rx_available(), 2)
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        self.assertEqual(xb.rx_available(), 1)
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')
        self.assertEqual(xb.rx_available(), 0)


    @async_test
    def testSendToSelfNoWaiting(self):
        xb = self.xb
        yield from xb.start()
        self.assertEqual(xb.rx_available(), 0)
        yield from xb.tx('foo', xb.address)
        yield from xb.tx('bar', xb.address)
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')


    #@unittest.skip('takes 3 seconds')
    @async_test
    def testSendToNonExistentAddress(self):
        print("this takes 3 seconds: ", end='')
        xb = self.xb
        yield from xb.start()
        self.assertEqual(xb.rx_available(), 0)
        v = yield from asyncio.wait_for(xb.tx('bar1', 'thisisanaddress!'), 4)
        print("1:", v)
        f = yield from xb.tx('bar2', 'thisisanaddress!')
        self.assertIsInstance(f, asyncio.Future)
        v = yield from asyncio.wait_for(f, 4)
        print("2:", v)


        with self.assertRaises(asyncio.TimeoutError):
            f = yield from xb.tx('bar3', 'thisisanaddress!')
            self.assertIsInstance(f, asyncio.Future)
            v = yield from asyncio.wait_for(f, 0.1)
            print("3:", v)

        t0 = pyb.millis()
        with self.assertRaises(asyncio.TimeoutError):
            v = yield from asyncio.wait_for(xb.tx('bar4', 'thisisanaddress!'), 0.1)
            print("4:", v)

        return


        yield from xb.tx('foo', 'thisisanaddress!')
        yield from asyncio.sleep(3)
        self.assertEqual(xb.rx_available(), 0)

    @async_test
    def testTxAndWaitOnStatus(self):
        #logging.basicConfig(logging.DEBUG)
        #print("0: q =", self.loop.q)
        xb = self.xb
        yield from xb.start()
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        #print("1: q =", self.loop.q)
        f0 = yield from xb.tx('foo', xb.address)
        #print("2: q =", self.loop.q)
        self.assertIsInstance(f0, asyncio.Future)
        self.assertFalse(f0.done())
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        result_0 = yield from asyncio.wait_for(f0, None)
        self.assertTrue(f0.done())
        #print("3: q =", self.loop.q)
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        self.assertEqual(result_0, f0.result())
        self.assertEqual(result_0, bytes(3))
        yield
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        
        t1 = millis()
        f1 = yield from xb.tx('bar', xb.address)
        self.assertIsInstance(f1, asyncio.Future)
        self.assertIsNot(f1, f0)
        result_1 = yield from asyncio.wait_for(f1, None)
        self.assertTrue(3 < elapsed_millis(t1) < 7)
        #print(elapsed_millis(t1))
        self.assertEqual(result_1, bytes(3))
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')
        self.assertEqual(xb.rx_available(), 0)


    def testZ(self):
        #logging.basicConfig(logging.DEBUG)

        @asyncio.coroutine
        def fun(t):
            yield from asyncio.sleep(t)

        tasks = [asyncio.async(fun(0.01))]
        self.loop.run_until_complete(asyncio.wait(tasks))


    @unittest.skip("obsolete")
    def test_get_frame(self):
        #logging.basicConfig(logging.DEBUG)
        #self.xb.verbose = True
        self.loop.run_until_complete(asyncio.async(self.xb.start()))
        self.assertTrue(self.xb.started)
        self.v = None

        @asyncio.coroutine
        def getv():
            yield from asyncio.sleep(0.01)
            t = yield from self.xb.xcvr.get_frame()
            self.assertEqual(t[-5:], b'\xff\xfe\x00\x00\x00') # The TX status
            self.v = yield from self.xb.xcvr.get_frame()     # The received packet

        @asyncio.coroutine
        def test():
            xb = self.xb
            self.assertEqual(xb.rx_available(), 0)
            yield from xb.tx('foo', xb.address)
            yield from asyncio.sleep(0.02)
            self.assertEqual(xb.rx_available(), 1)
            self.assertEqual(self.v[-3:], b'foo')

        tasks = [asyncio.async(getv()), asyncio.async(test())]
        #print("tasks is %r" % tasks)
        self.loop.run_until_complete(asyncio.wait(tasks))


    

def gse():
    test_as(create_test_radio('gse'))

def flight():
    test_as(create_test_radio('flight'))

def create_test_radio(r):
    if r == 'gse': 
        return XBRadio(spi = SPI(1),
                       nRESET = Pin('Y11'),
                       DOUT = Pin('Y12'),
                       nSSEL = Pin('X5'),
                       nATTN = Pin('Y10'))
    if r == 'flight' or r == 'flt':
        return XBRadio(spi = SPI(2),
                       nRESET = Pin('X11'),
                       DOUT = Pin('X12'),
                       nSSEL = Pin('Y5'),
                       nATTN = Pin('Y4'))

def create_test_radio_by_dialog(r):
    while True:
        r = input('Is this GSE or Flight? ').lower()
        v = create_test_radio(r)
        if v:
            return v

print('XBee radio test module loaded')
False and print(
"""XBee pinout for:	GSE	Flight
			---	------
DOUT (pin 2)		Y12	X12
SPI_MISO (pin 4)	X7	Y7
nRESET (pin 5)		Y11	X11
SPI_MOSI (pin 11)	X8	Y8
SPI_nSSEL (pin 17)	X5	Y5
SPI_CLK (pin 18)	X6	Y6
SPI_nATTN (pin 19)	Y10	Y4 (not X10)
""")

if __name__ == '__main__':
    unittest.main()
