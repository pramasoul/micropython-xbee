"""Test for XBee Pro S3B"""

from xbradio import XBRadio
from pyb import SPI, Pin, delay

def test_as(xb):
    #xb.verbose = True
    #g = xb.get_and_process_available_packets
    #BUG, this doesn't work: print("values: %r" % xb.values)
    #print("values: %s" % str(xb.values))
    #print(':'.join('%x' % v for v in xb.address))
    at = xb.do_AT_cmd_and_process_response
    at('TP')
    assert 1 < xb.values['TP'] < 60, "bad temperature %d" % xb.values['TP']
    at('%V')
    assert 3200 < xb.values['%V'] < 3400, "bad voltage %d" % xb.values['%V']
    at('ER')
    #print("values: %s" % str(xb.values))
    assert xb.rx_available() == 0
    xb.tx('bar', xb.address)
    delay(5)
    assert xb.rx_available() == 1
    xb.tx('blort', xb.address)
    delay(100)
    assert xb.rx_available() == 2
    a, d = xb.rx()
    #print("From %s got %r" % (':'.join('%x' % v for v in xb.address), d))
    assert a == xb.address
    assert d == b'bar', "Expected 'bar', got %r" % d
    assert xb.rx_available() == 1
    a, d = xb.rx()
    #print("From %s got %r" % (':'.join('%x' % v for v in xb.address), d))
    assert a == xb.address
    assert d == b'blort', "Expected b'blort, got %r" % d
    assert xb.rx_available() == 0
    xb.tx('foo', 'thisisanaddress!')
    delay(3000)
    assert xb.rx_available() == 0
    

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

"""
def master():
    nrf = NRF24L01(SPI(2), Pin('Y5'), Pin('Y4'), payload_size=8)

    nrf.open_tx_pipe(pipes[0])
    nrf.open_rx_pipe(1, pipes[1])
    nrf.start_listening()

    num_needed = 16
    num_successes = 0
    num_failures = 0
    led_state = 0

    print('NRF24L01 master mode, sending %d packets...' % num_needed)

    while num_successes < num_needed and num_failures < num_needed:
        # stop listening and send packet
        nrf.stop_listening()
        millis = pyb.millis()
        led_state = max(1, (led_state << 1) & 0x0f)
        print('sending:', millis, led_state)
        try:
            nrf.send(struct.pack('ii', millis, led_state))
        except OSError:
            pass

        # start listening again
        nrf.start_listening()

        # wait for response, with 250ms timeout
        start_time = pyb.millis()
        timeout = False
        while not nrf.any() and not timeout:
            if pyb.elapsed_millis(start_time) > 250:
                timeout = True

        if timeout:
            print('failed, respones timed out')
            num_failures += 1

        else:
            # recv packet
            got_millis, = struct.unpack('i', nrf.recv())

            # print response and round-trip delay
            print('got response:', got_millis, '(delay', pyb.millis() - got_millis, 'ms)')
            num_successes += 1

        # delay then loop
        pyb.delay(250)

    print('master finished sending; succeses=%d, failures=%d' % (num_successes, num_failures))

def slave():
    nrf = NRF24L01(SPI(2), Pin('Y5'), Pin('Y4'), payload_size=8)

    nrf.open_tx_pipe(pipes[1])
    nrf.open_rx_pipe(1, pipes[0])
    nrf.start_listening()

    print('NRF24L01 slave mode, waiting for packets... (ctrl-C to stop)')

    while True:
        pyb.wfi()
        if nrf.any():
            while nrf.any():
                buf = nrf.recv()
                millis, led_state = struct.unpack('ii', buf)
                print('received:', millis, led_state)
                for i in range(4):
                    if led_state & (1 << i):
                        pyb.LED(i + 1).on()
                    else:
                        pyb.LED(i + 1).off()
                pyb.delay(15)

            nrf.stop_listening()
            try:
                nrf.send(struct.pack('i', millis))
            except OSError:
                pass
            print('sent response')
            nrf.start_listening()
"""
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

run xbradio_test.gse() on GSE, then xbradio_test.flight() on Flight')
""")

