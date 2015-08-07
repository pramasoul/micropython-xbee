"""Test for asyncio-based XBee Pro S3B library"""

import asyncio
import unittest
#from ubinascii import hexlify

from async_xbradio import XBRadio
from pyb import SPI, Pin, info


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        future = coro(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(future)
    return wrapper


class CoroTestCase(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        #self.loop = asyncio.get_event_loop()
        #asyncio.set_event_loop(None)
        asyncio.set_event_loop(self.loop)
        
    def tearDown(self):
        pass

    @async_test
    def testWrap(self):
        v = 1
        yield from asyncio.sleep(0.1, loop=self.loop)
        v = 2
        self.assertEqual(v, 2)


class RadioTestCase(unittest.TestCase):

    def setUp(self):
        self.xb = create_test_radio('gse')
        self.loop = asyncio.new_event_loop()
        #asyncio.set_event_loop(None)
        asyncio.set_event_loop(self.loop)
        
    def tearDown(self):
        pass

    def testIsRadio(self):
        self.assertIsInstance(self.xb, XBRadio)

    @async_test
    def testSleep(self):
        yield from asyncio.sleep(0.01)

    @async_test
    def testStartRadio(self):
        yield from self.xb.start()
        self.assertTrue(self.xb.started)

    @async_test
    def testAddress(self):
        #self.xb.verbose = True
        #self.xb.xcvr.verbose = True
        yield from self.xb.start()
        self.assertIsInstance(self.xb.address, bytes)
        self.assertNotEqual(sum(self.xb.address), 0)

    @async_test
    def testATcmds(self):
        xb = self.xb
        yield from xb.start()
        at = xb.do_AT_cmd_and_process_response
        yield from at('TP')
        self.assertTrue(1 < xb.values['TP'] < 60, "bad temperature %d" % xb.values['TP'])
        yield from at('%V')
        self.assertTrue(3200 < xb.values['%V'] < 3400, "bad voltage %d" % xb.values['%V'])
        
    @async_test
    def testRxErrorCount(self):
        xb = self.xb
        yield from xb.start()
        at = xb.do_AT_cmd_and_process_response
        yield from at('ER')

    @async_test
    def testSendToSelf(self):
        xb = self.xb
        yield from xb.start()
        self.assertEqual((yield from xb.rx_available()), 0)
        yield from xb.tx('foo', xb.address)
        yield from asyncio.sleep(0.005)
        self.assertEqual((yield from xb.rx_available()), 1)
        yield from xb.tx('bar', xb.address)
        yield from asyncio.sleep(0.1)
        self.assertEqual((yield from xb.rx_available()), 2)
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        self.assertEqual((yield from xb.rx_available()), 1)
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')
        self.assertEqual((yield from xb.rx_available()), 0)

    @unittest.skip('takes 3 seconds')
    @async_test
    def testSendToNonExistentAddress(self):
        print("this takes 3 seconds: ", end='')
        xb = self.xb
        self.assertEqual((yield from xb.rx_available()), 0)
        yield from xb.tx('foo', 'thisisanaddress!')
        yield from asyncio.sleep(3)
        self.assertEqual((yield from xb.rx_available()), 0)


    

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
