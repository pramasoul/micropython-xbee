"""Test for XBee Pro S3B"""

import unittest
from xbradio import XBRadio
from pyb import SPI, Pin, delay


class RadioTestCase(unittest.TestCase):

    def setUp(self):
        self.xb = create_test_radio('gse')
        
    def tearDown(self):
        pass

    def testAddress(self):
        self.assertIsInstance(self.xb.address, bytes)
        self.assertNotEqual(sum(self.xb.address), 0)

    def testATcmds(self):
        xb = self.xb
        at = xb.do_AT_cmd_and_process_response
        at('TP')
        self.assertTrue(1 < xb.values['TP'] < 60, "bad temperature %d" % xb.values['TP'])
        at('%V')
        self.assertTrue(3200 < xb.values['%V'] < 3400, "bad voltage %d" % xb.values['%V'])
        
    @unittest.skip('not done')
    def testRxErrorCount(self):
        xb = self.xb
        at = xb.do_AT_cmd_and_process_response
        at('ER')

    def testSendToSelf(self):
        xb = self.xb
        self.assertEqual(xb.rx_available(), 0)
        xb.tx('foo', xb.address)
        delay(5)
        self.assertEqual(xb.rx_available(), 1)
        xb.tx('bar', xb.address)
        delay(100)
        self.assertEqual(xb.rx_available(), 2)
        a, d = xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        self.assertEqual(xb.rx_available(), 1)
        a, d = xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')
        self.assertEqual(xb.rx_available(), 0)

    def testSendToNonExistentAddress(self):
        xb = self.xb
        self.assertEqual(xb.rx_available(), 0)
        xb.tx('foo', 'thisisanaddress!')
        delay(3000)
        self.assertEqual(xb.rx_available(), 0)


    

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
print(
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
