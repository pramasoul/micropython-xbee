"""Test for asyncio-based XBee Pro S3B library"""

import logging
import unittest

from ubinascii import hexlify, unhexlify

from asyncio_4pyb import new_event_loop, set_event_loop, get_event_loop, \
    EventLoop

from async_xbradio import Future, TimeoutError, \
    coroutine, sleep, wait_for

from async_xbradio import XBRadio, \
    FrameOverrunError, FrameWaitTimeout

from pyb import SPI, Pin, info, millis, elapsed_millis, micros, elapsed_micros

log = logging.getLogger("test")

_test_EventLoop = None

_role = None

def async_test(f):
    def wrapper(*args, **kwargs):
        global _test_EventLoop
        coro = coroutine(f)
        #loop = get_event_loop()
        loop = _test_EventLoop
        #print("wrapper loop %r" % loop)
        assert isinstance(loop, EventLoop)
        #pyb.LED(1).on()
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper


class CoroTestCase(unittest.TestCase):

    def setUp(self):
        global _test_EventLoop
        #print('(setUp', end='')
        was_loop = _test_EventLoop
        self.loop = new_event_loop()
        _test_EventLoop = self.loop
        assert _test_EventLoop is self.loop
        assert self.loop is not was_loop

        #XBRadio uses default loop:
        set_event_loop(self.loop)
        #set_event_loop(None)


        #assert _def_event_loop is self.loop
        #assert self.loop is get_event_loop()
        #assert len(self.loop.q) == 0
        #print(')')

    def tearDown(self):
        pass

    @async_test
    def testWrap(self):
        # Tests that the async_test wrapper works
        v = 1
        yield from sleep(0.1)
        v = 2
        self.assertEqual(v, 2)


class RadioTestCase(unittest.TestCase):

    def setUp(self):
        global _test_EventLoop
        global _role
        logging.basicConfig(logging.INFO)
        # We use a new loop each time, for isolation between tests
        self.loop = new_event_loop()
        _test_EventLoop = self.loop
        # XBRadio assumes default loop, so set here
        set_event_loop(self.loop)
        #self.xb = create_test_radio('gse')
        self.xb = create_test_radio(_role)
        
    def tearDown(self):
        logging.basicConfig(logging.INFO)
        if __debug__:
            log.debug("loop.q length %d", len(self.loop.q))

    def testIsRadio(self):
        # We have a radio object
        self.assertIsInstance(self.xb, XBRadio)

    @async_test
    def testSleep(self):
        # sleep() does not freeze
        yield from sleep(0.01)

    @async_test
    def testStartRadio(self):
        # The radio can be started
        yield from self.xb.start()
        self.assertTrue(self.xb.started)

    @async_test
    def testAddress(self):
        # When started, the radio has an address
        yield from self.xb.start()
        self.assertIsInstance(self.xb.address, bytes)
        self.assertNotEqual(sum(self.xb.address), 0)

    @async_test
    def testATcmds(self):
        # AT commands work
        xb = self.xb
        yield from xb.start()
        temp = yield from xb.AT_cmd('TP')
        self.assertTrue(1 < temp < 60, "bad temperature %d" % temp)
        voltage = yield from xb.AT_cmd('%V')
        self.assertTrue(3200 < voltage < 3400, "bad voltage %d" % voltage)


    @async_test
    def testRxErrorCount(self):
        xb = self.xb
        yield from xb.start()
        error_count = yield from xb.AT_cmd('ER')
        self.assertEqual(error_count, 0)
        

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
        self.assertTrue(34 <= et < 45, "took %dms (expected 34ms)" % et)


    @async_test
    def testSendToSelf(self):
        #logging.basicConfig(logging.DEBUG)
        xb = self.xb
        yield from xb.start()
        self.assertEqual(xb.rx_available(), 0)
        yield from xb.tx('foo', xb.address)
        yield from sleep(0.01)
        self.assertEqual(xb.rx_available(), 1)
        yield from xb.tx('bar', xb.address)
        yield from sleep(0.1)
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
        yield from wait_for((yield from xb.tx('foo', xb.address)), 0.1)
        yield from wait_for((yield from xb.tx('bar', xb.address)), 0.1)
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        a, d = yield from xb.rx()
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')


    #@unittest.skip('takes 10 seconds')
    @async_test
    def testSendToNonExistentAddress(self):
        print("this takes about 10 seconds: ", end='')
        t_start = self.loop.time()
        xb = self.xb
        yield from xb.start()
        self.assertEqual(xb.rx_available(), 0)
        t0 = self.loop.time()
        txrv1 = yield from xb.tx('bar1', 'thisisanaddress!')
        self.assertIsInstance(txrv1, Future, 'got %r (expected a Future)' % txrv1)
        self.assertFalse(txrv1.done())
        v1 = yield from wait_for(txrv1)
        t1 = self.loop.time()
        self.assertTrue(txrv1.done())
        self.assertTrue(1 < t1-t0 < 3)
        t0 = self.loop.time()
        #No: v2 = yield from wait_for(xb.tx('bar2', 'thisisanaddress!'))
        #Syntax error: v2 = yield from wait_for(yield from xb.tx('bar2', 'thisisanaddress!'))
        v2 = yield from wait_for((yield from xb.tx('bar2', 'thisisanaddress!')))
        t1 = self.loop.time()
        self.assertEqual(v2, v1)
        #print(t1-t0)
        self.assertTrue(1 < t1-t0 < 3)
        print(v2)

        # 4 seconds is long enough to get a failure
        v = yield from wait_for((yield from xb.tx('bar2', 'thisisanaddress!')), 4)
        self.assertEqual(v, v1)

        # 0.1 seconds is not long enough, and raises TimeoutError
        with self.assertRaises(TimeoutError):
            v = yield from wait_for((yield from xb.tx('bar3', 'thisisanaddress!')), 0.1)

        t_end = self.loop.time()
        print("took", t_end - t_start, "seconds")
        return


        with self.assertRaises(TimeoutError):
            f = yield from xb.tx('bar3', 'thisisanaddress!')
            self.assertIsInstance(f, Future)
            v = yield from wait_for(f, 0.1)
            print("3:", v)

        t0 = millis()
        with self.assertRaises(TimeoutError):
            v = yield from wait_for(xb.tx('bar4', 'thisisanaddress!'), 0.1)
            print("4:", v)


        yield from xb.tx('foo', 'thisisanaddress!')
        yield from sleep(3)
        self.assertEqual(xb.rx_available(), 0)


    @async_test
    def testTxAndWaitOnStatus(self):
        #logging.basicConfig(logging.DEBUG)
        #print("0: q =", self.loop.q)
        xb = self.xb
        yield from xb.start()

        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        #print("1: q =", self.loop.q)
        f0 = yield from xb.tx('foo', xb.address) # send to self
        #print("2: q =", self.loop.q)
        #print(repr(Future))

        self.assertIsInstance(f0, Future)
        self.assertFalse(f0.done())
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        result_0 = yield from wait_for(f0, None)
        self.assertTrue(f0.done())
        #print("3: q =", self.loop.q)
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        self.assertEqual(result_0, f0.result())
        self.assertEqual(result_0, bytes(3))
        #print("4: q =", self.loop.q)
        #yield
        #print("5: q =", self.loop.q)
        #print("frame_wait: ", list((i,v) for i,v in enumerate(xb.frame_wait) if v))
        
        t1 = millis()
        f1 = yield from xb.tx('bar', xb.address)
        self.assertIsInstance(f1, Future)
        self.assertIsNot(f1, f0)
        #print("6: q =", self.loop.q)
        result_1 = yield from wait_for(f1, None)
        d1 = elapsed_millis(t1)
        self.assertTrue(3 < d1 < 12, "took %dms" % d1)
        #print("7: q =", self.loop.q)
        #print(elapsed_millis(t1))
        self.assertEqual(result_1, bytes(3))
        a, d = yield from xb.rx()
        #print("8: q =", self.loop.q)
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'foo')
        a, d = yield from xb.rx()
        #print("9: q =", self.loop.q)
        self.assertEqual(a, xb.address)
        self.assertEqual(d, b'bar')
        self.assertEqual(xb.rx_available(), 0)


    @unittest.skip("obsolete")
    def test_get_frame(self):
        #logging.basicConfig(logging.DEBUG)
        self.loop.run_until_complete(async(self.xb.start()))
        self.assertTrue(self.xb.started)
        self.v = None

        @coroutine
        def getv():
            yield from sleep(0.01)
            t = yield from self.xb.xcvr.get_frame()
            self.assertEqual(t[-5:], b'\xff\xfe\x00\x00\x00') # The TX status
            self.v = yield from self.xb.xcvr.get_frame()     # The received packet

        @coroutine
        def test():
            xb = self.xb
            self.assertEqual(xb.rx_available(), 0)
            yield from xb.tx('foo', xb.address)
            yield from sleep(0.02)
            self.assertEqual(xb.rx_available(), 1)
            self.assertEqual(self.v[-3:], b'foo')

        tasks = [async(getv()), async(test())]
        #print("tasks is %r" % tasks)
        self.loop.run_until_complete(wait(tasks))

    @async_test
    def testInfo(self):
        # Can get various info
        xb = self.xb
        yield from xb.start()
        print("\nVersion %s, hardware %d, firmware %d" % \
              ((yield from xb.AT_cmd('VL')),
               (yield from xb.AT_cmd('HV')),
               (yield from xb.AT_cmd('VR'))))
        print("Address %s" % str(hexlify(xb.address), 'ASCII'))


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

def interact(role):

    class GotEOT(Exception):
        pass

    @coroutine
    def readline():
        buf = b''
        while console.isconnected():
            if console.any():
                c = console.read(1)
                if c == b'\x04':
                    raise GotEOT
                elif c == b'\r' or c == b'\n':
                    console.write(b'\r\n')
                    return buf
                else:
                    buf += c
                    console.write(c)
            else:
                yield from sleep(0.05)

    @coroutine
    def write(buf):
        console.write(buf)
        yield

    @coroutine
    def writeln(buf):
        yield from write(buf)
        yield from write(b'\r\n')


    @coroutine
    def interpret(line):
        #yield from write(b'got "' + line + '"\r\n')
        if not line:
            return

        cmd, _, rol = line.partition(b' ')
        cmd = str(cmd, 'ASCII')
        rol = rol.lstrip()

        if cmd == 'info':
            yield from writeln('addr %r' % hexlify(xb.address))

        elif cmd == 'tx':
            addr, _, payload = rol.partition(b':')
            address = unhexlify(addr)
            yield from write('sending %d bytes to %r...' % \
                               (len(payload), address))
            status = yield from wait_for((yield from xb.tx(payload, address)))
            yield from writeln('status %r' % status)

        elif cmd == 'rx':
            a, d = yield from xb.rx()
            yield from writeln('from %s got %r' % \
                               (str(hexlify(a), 'ASCII'), d))

        elif cmd in ('quit', 'exit', 'bye'):
            raise GotEOT


    @coroutine
    def repl(xb):
        yield from xb.start()
        while(console.isconnected()):
            prompt = bytes(role + '> ', 'ASCII')
            #console.write(prompt)
            yield from write(prompt)
            try:
                line = yield from readline()
                yield from interpret(line)
            except GotEOT:
                return

    console = pyb.USB_VCP()
    xb = create_test_radio(role)
    loop = new_event_loop()
    set_event_loop(loop)
    loop.run_until_complete(repl(xb))



def main():
    global _role
    _role = open('xbradio.cfg').read().strip()
    unittest.main()
    interact(_role)

if __name__ == '__main__':
    main()
