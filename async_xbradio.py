"""asyncio-based XBRadio"""

from asyncio_4pyb import Future, TimeoutError, \
    coroutine, sleep, wait_for

import logging

log = logging.getLogger("xbradio")

from pyb import SPI, Pin
from pyb import millis, elapsed_millis


class RadioException(Exception):
    pass

class FrameWaitTimeout(RadioException):
    pass

class SpiCommError(RadioException):
    pass

class FrameOverrunError(RadioException):
    pass

class ATStatusError(RadioException):
    pass

class PacketException(Exception):
    pass

class ChecksumError(PacketException):
    pass


def big_endian_int(b):
    rv = 0
    for v in list(b):
        rv = (rv << 8) + int(v)
    return rv


class FrameBuffer(object):
    # A helper class that accepts bytes received from an XBee,
    # identifies frames, stores them in a queue, and provides
    # them from the queue on request

    def __init__(self):
        self.frames = []
        self.reset_parse()
        self.total_marking_bytes_count = 0
        self.marking_bytes_count = 0
        self.frame_count = 0

    def reset_parse(self):
        # States:
        # 0: looking for new frame
        # 1: found sync ('~')
        # 2: have first byte of payload length
        # 3: have payload length, gathering payload
        # 4: have full payload, need check byte
        self.state = 0
        self.frame_buf = b''

    def __len__(self):
        return len(self.frames)

    def __iter__(self):
        return iter(self.frames)

    def dequeue_one(self):
        return self.frames.pop(0)

    def include_bytes(self, b):
        while len(b):
            if self.state is 0:
                marking, sync, b = b.partition(b'~')
                self.total_marking_bytes_count += len(marking)
                if sync:
                    self.marking_bytes_count = 0
                    self.state = 1
                else:
                    self.marking_bytes_count += len(marking)
            if self.state is 1:
                if len(b):
                    self.payload_length = b[0]
                    b = b[1:]
                    self.state = 2
            if self.state is 2:
                if len(b):
                    self.payload_length <<= 8
                    self.payload_length += b[0]
                    b = b[1:]
                    self.state = 3
            if self.state is 3:
                # Try to get the bytes we need to make the length
                want = self.payload_length - len(self.frame_buf)
                self.frame_buf += b[:want]
                b = b[want:]
                if len(self.frame_buf) == self.payload_length:
                    self.state = 4
            if self.state is 4:
                if len(b):
                    check_byte = b[0]
                    b = b[1:]
                    if (sum(self.frame_buf) & 0xff) + check_byte != 0xff:
                        self.bad = (self.frame_buf, check_byte)
                        self.reset_parse()
                        raise ChecksumError("sum(frame) = 0x%x, check_byte = 0x%x" \
                                          % (sum(self.bad[0]), self.bad[1]))
                    self.frames.append(self.frame_buf)
                    self.frame_count += 1
                    self.frame_buf = b''
                    self.state = 0

    def in_a_frame(self):
        return bool(self.state)


# Hardware interface
class XBRHAL:
    #atplzero = b'\x08\x03PL\x00'
    #int_AT = set('DB,TP,%V,PL'.split(','))
    #str_AT = set('NI,VL'.split(','))
    
    def __init__(self, spi, nRESET, DOUT, nSSEL, nATTN):

        # init the SPI bus and pins
        # XBee Pro manual says (p22) "SPI Clock rates up to 3.5 MHz are possible"
        #spi.init(SPI.MASTER, baudrate=3000000, polarity=0)
        # But this leads to too-frequent wedging, requiring a force_SPI to get unstuck
        # So we use an experimentally-derived lower frequency
        # The running frequency is actually determined by the prescale, a
        # power-of-two divisor of the APB bus frequency.
        # prescaler=256 with delay_after_nATTN=1 ok (tested 340k frames)
        # prescaler=128 with delay_after_nATTN=0 ok (tested 310k frames)
        # prescaler=64 failed after of order 1000 frames
        spi.init(SPI.MASTER, prescaler=128, polarity=0)

        nRESET.init(nRESET.OUT_OD, nRESET.PULL_UP)
        DOUT.init(DOUT.OUT_OD, DOUT.PULL_UP)
        nSSEL.init(nSSEL.OUT_PP)
        nATTN.init(nATTN.IN, nATTN.PULL_UP)
        self.pins = (nRESET, DOUT, nSSEL, nATTN)
        for p in self.pins:
            p.high()

        # store the pins
        self.spi = spi
        self.nRESET = nRESET
        self.DOUT = DOUT
        self.nSSEL = nSSEL
        self.nATTN = nATTN

        # helper
        self.pb = FrameBuffer()

        # init tuneable parameters
        self.rx_hunk_len = 16

        self.verbose = False

    @coroutine
    def hard_reset(self):
        yield from self.force_SPI()
        self.pb = FrameBuffer() # start anew

    @coroutine
    def force_SPI(self):
        # reset and force the XBee into SPI mode
        self.nRESET.low()
        self.DOUT.low()
        yield from sleep(0.01) # IIRC noticably less than 10ms fails
        self.nRESET.high()
        #delay(100)              # Without nATTN watch loop, 85ms is unreliable. 100ms is ok.
        #t0 = millis()
        while self.nATTN.value():
            #yield from sleep(0.001)
            yield
        #print(elapsed_millis(t0))
        self.DOUT.high()
        
    @coroutine
    def get_frame(self, timeout=None):
        # Get a frame from the radio
        # or raise FrameWaitTimeout if none available in specified time

        @coroutine
        def get_frame_by_reading(limit=None):
            # Helper to get a packet from the radio itself
            # Note it will spin forever if the radio has no packet,
            # unless a limit of bytes to read is provided
            if __debug__ and self.verbose:
                log.debug("get_frame_by_reading(%d)", limit)
            self.nSSEL.low()
            gotten = 0
            while len(self.pb) == 0 and \
                  (limit is None or gotten < limit): # feed the packet buffer until packet(s) available
                self.pb.include_bytes(self.spi.recv(self.rx_hunk_len))
                gotten += self.rx_hunk_len
                yield
                if __debug__ and self.verbose:
                    log.debug("get_frame_by_reading(): State %d, gotten %d, marking bytes %d, total marking %d",
                              self.pb.state,
                              gotten,
                              self.pb.marking_bytes_count,
                              self.pb.total_marking_bytes_count)
            if limit and gotten >= limit:
                raise FrameOverrunError("got %d bytes and don't have a frame yet" % gotten)
            rv = self.pb.dequeue_one()
            if __debug__ and self.verbose:
                log.debug("get_frame_by_reading() returning %r", rv)
            return rv

        # From the packet buffer if available
        if len(self.pb):
            rv = self.pb.dequeue_one()
        # else if part way into a packet, get the rest
        elif self.pb.in_a_frame():
            rv = yield from get_frame_by_reading(300) # 300 exceeds max packet length
        # else see if one turns up within the timeout
        else:
            if self.nATTN.value():  # No data available from radio yet
                # wait up to the timeout value
                t0 = millis()
                while self.nATTN.value():
                    yield
                    if timeout is not None and elapsed_millis(t0) > timeout:
                        raise FrameWaitTimeout("%dms" % timeout)
                # Here nATTN is in asserted state
            assert not self.nATTN.value(), 'expected nATTN to be asserted (low)'
            rv = yield from get_frame_by_reading(300)
        if __debug__ and self.verbose:
            log.debug("get_frame() returning %r", rv)
        return rv


    @coroutine
    def send_frame(self, buf):
        # Wrap buffer contents in an API frame and send to the radio
        # Radio may be sending a frame to us at the same time
        if __debug__ and self.verbose:
            log.debug("send_frame(%r)", buf)
        header = bytearray(3)
        hv = memoryview(header)
        hv[0] = ord('~')
        hv[1] = len(buf) >> 8
        hv[2] = len(buf) & 0xff
        self.nSSEL.low()
        self.pb.include_bytes(self.spi.send_recv(header))
        self.pb.include_bytes(self.spi.send_recv(buf))
        self.pb.include_bytes(self.spi.send_recv(0xff - (sum(buf) & 0xff)))
        yield                   # FIXME: should this be async at all?
        
    # for debugging
    def show(self):
        print('nRESET: %d, DOUT: %d, nSSEL: %d, nATTN: %d' \
              % (self.nRESET.value(),
                 self.DOUT.value(),
                 self.nSSEL.value(),
                 self.nATTN.value()))


class XBRadio:
    #atplzero = b'\x08\x03PL\x00'
    int_AT = set('%V,DB,ER,GD,HV,ID,PL,TP,VR'.split(',')) # AT commands that have integer responses
    str_AT = set('NI,VL'.split(',')) # AT commands that have string responses

    def __init__(self, spi, nRESET, DOUT, nSSEL, nATTN):
        self.xcvr = XBRHAL(spi, nRESET, DOUT, nSSEL, nATTN)
        self.received_data_packets = []
        self.received_data_future = None
        self.frame_sequence = 1
        self.address = bytearray(8)
        self.values = {}
        #self.correspondent_address = bytes(16)
        self.frame_wait = [None] * 256 # a place for futures indexed by frame ID


	# set up packet parsing dispatch functions
        # 0x88 AT Command Response
        # 0x8A Modem Status
        # 0x8B Transmit Status
        # 0x90 RX Indicator (AO=0)
        # 0x91 Explicit Rx Indicator (AO=1)
        # 0x95 Node Identification Indicator (AO=0)
        # 0x97 Remote Command Response

        self.frame_dispatch = { 0x88: self.consume_AT_response,
                                0x8a: self.consume_modem_status,
                                0x8b: self.consume_transmit_status,
                                0x90: self.consume_rx
        }
        
        self.verbose = False
        self.started = False

    @coroutine
    def start(self):
        t0 = millis()
        yield from self.xcvr.hard_reset()
        yield self.get_and_process_frames() # start this task
        self.address = yield from self.get_MAC_from_radio()
        self.started = True

    @coroutine
    def reset(self):
        yield from self.xcvr.hard_reset()
        #FIXME: kill existing get_and_process_frames() if any

    @coroutine
    def get_and_process_frames(self):
        # Continuously consume and process packets from radio
        while True:
            b = yield from self.xcvr.get_frame()
            if  __debug__ and self.verbose:
                # FIXME: better conditioning, or figure out how
                #  to have __debug__ not True
                log.debug("g_a_p_f(): %s", self.str_response_frame(b))
            v = self.process_frame(b)
            if v and __debug__ and self.verbose:
                log.debug("packet not consumed: %s", self.str_response_frame(b))

    def process_frame(self, b):
        # Returns None if the frame was consumed, else returns the frame
        frame_type = b[0]
        if frame_type in self.frame_dispatch:
            return self.frame_dispatch[frame_type](b)
        else:
            return b

    def _frame_done(self, fs, result=None):
        fut = self.frame_wait[fs]
        #print("setting result for frame #%d %r to %r" % (fs, fut, result))
        assert isinstance(fut, Future)
        assert not fut.done()
        fut.set_result(result)
        self.frame_wait[fs] = None

    def consume_modem_status(self, b):
        self.modem_status = b[1]

    def consume_transmit_status(self, b):
        #print('{c_t_x(%r)}' % b)        # DEBUG
        if (b[4] | b[5]):       # A retransmit or a status problem
            log.info(self.str_response_frame(b))
        self._frame_done(b[1], b[4:])

    def consume_rx(self, b):
        # Parse out (address, data) from a received RF packet and provide to
        # present or subsequent reader in a fifo
        v = (b[1:9], b[12:])
        self.received_data_packets.insert(0, v) # appendleft
        rdf = self.received_data_future
        #log.info("consume_rx: v=%r, rdf=%r", v, rdf)
        if rdf and not rdf.done():
            rdf.set_result(None) # future is hereby satisfied

    def consume_AT_response(self, b):
        # Function applied to AT response packets
        # returns its arg if not consumed
        rv = None
        cmd = str(b[2:4], 'ASCII')
        #print("Got AT response: %s" % cmd)
        status = b[4]
        if status is not 0:
            log.debug(self.str_response_frame(b))
            v = ATStatusError('AT response status %d' % status) # DEBUG
        else:
            data = b[5:]
            if cmd in self.int_AT:
                v = big_endian_int(data)
            elif cmd in self.str_AT:
                v = str(data, 'ASCII')
            else:
                v = data
        self._frame_done(b[1], v)


    def next_frame_sequence(self):
        self.frame_sequence += 1
        self.frame_sequence &= 0xff
        if not self.frame_sequence:
            self.frame_sequence = 1
        return self.frame_sequence

    @coroutine
    def send_AT_cmd(self, cmd, param=None):
        # Returns a future that completes to the value
        b = bytes([0x08, self.next_frame_sequence()])
        if isinstance(cmd, str):
            cmd = bytes(cmd, 'ASCII')
        b += cmd
        if param is not None:
            if not isinstance(param, (bytes, bytearray)):
                if isinstance(param, int):
                    param = bytes([param])
                elif isinstance(param, str):
                    param = bytes(param, 'ASCII')
                else:
                    param = bytes(param)
            b += param
        return (yield from self.send_frame_return_future(b))
        
    @coroutine
    def AT_cmd(self, cmd, param=None, timeout=None):
        # Returns the value, or times out, or raises exception
        #return (yield from wait_for((yield from self.send_AT_cmd(cmd, param)), timeout))
        v = yield from wait_for((yield from self.send_AT_cmd(cmd, param)), timeout)
        if isinstance(v, Exception):
            raise(v)
        return v

    @coroutine
    def get_MAC_from_radio(self):
        vh = yield from wait_for((yield from self.send_AT_cmd('SH')))
        vl = yield from wait_for((yield from self.send_AT_cmd('SL')))
        return vh + vl

    @coroutine
    def send_frame_return_future(self, b):
        # Sends a frame and returns a future that is completed when
        # the corresponding response frame is received from the radio
        # The frameID is required and assumed to be the second byte
        fs = b[1]
        frame_wait = self.frame_wait
        if frame_wait[fs]:
            log.info("A frame still waiting in slot %d: %r" \
                     % (fs, frame_wait[fs]))
            
            # FIXME: do something with the old future

        # FIXME this creation of a Future ties us to the default eventloop:
        fut = Future()  # Don't know our loop so must take default

        frame_wait[fs] = fut 
        yield from self.xcvr.send_frame(b)
        return fut

    @coroutine
    def tx(self, data, dest_address=None, ack=True):
        # Transmit an RF packet
        if ack:
            options = 0x00
        else:
            options = 0x01
        if dest_address is None:
            dest_address = self.correspondent_address
        fs = self.next_frame_sequence()
        b = bytes([0x10, fs])
        b += dest_address
        b += bytes([0xFF, 0xFE, # "Reserved"
                    0x00,       # use max broadcast radius
                    options])
        b += data
        #print("tx %s ..." % p[:16]) # DEBUG
        rv = yield from self.send_frame_return_future(b)
        return rv


    @coroutine
    def rx(self, timeout=1):
        # return next available (address, data) received
        #print("rx(timeout=%d): len(received_data_packets) = %d"
        #      % (timeout, len(self.received_data_packets))) # DEBUG
        #***
        # FIXME: Don't spin, use wait_for
        while True:
            try:
                return self.received_data_packets.pop()
            except IndexError:
                # DEBUG                
                #yield
                #continue
                # This would not be safe in multi-threaded env,
                # so take care that interrupt handlers don't
                # mess with received_data_future or
                # received_data_packets (else harden this code)
                # Were the fifo-filler to run right now, we
                # could get hanged
                if self.received_data_future is None \
                   or self.received_data_future.done():
                    self.received_data_future = Future()
                #DEBUG yield from wait_for(self.received_data_future, 1)
                yield from wait_for(self.received_data_future)

    @coroutine
    def will_rx(self):
        x = self.xcvr
        rv = None
        while not rv:
            b = yield from x.get_frame()
            
    def rx_available(self):
        return len(self.received_data_packets)


    ################################################################
    # Visibility and debugging

    response_names = { 0x88: "AT Command Response",
                       0x8A: "Modem Status",
                       0x8B: "Transmit Status",
                       0x90: "RX Indicator (AO=0)",
                       0x91: "Explicit Rx Indicator (AO=1)",
                       0x95: "Node Identification Indicator (AO=0)",
                       0x97: "Remote Command Response" }

    def print_response_frame(self, frame):
        print(self.str_response_frame(frame))

    def str_response_frame(self, frame):
        frame_type = frame[0]
        try:
            s = "%s:" % self.response_names[frame_type]
        except KeyError:
            return "Unk frame %r" % frame

        if frame_type == 0x88:
            s += (" id 0x%x %s %s" %
                  (frame[1],
                   str(frame[2:4], 'ASCII'),
                   ["OK", "ERR", "Invalid Cmd", "Invalid Param"][frame[4]]))
            if len(frame) > 5:
                s += (" %s" % ' '.join("%x" % v for v in frame[5:]))

        elif frame_type == 0x8a:
            s += (" %s" % { 0x00: "HW reset",
                            0x01: "Watchdog reset",
                            0x0b: "Network Woke Up",
                            0x0c: "Network Went To Sleep" }[frame[1]])

        elif frame_type == 0x8b:
            s += (" id 0x%x, %d retries, %s, %s" %
                  (frame[1],
                   frame[4],
                   { 0x00: "Success",
                     0x01: "MAC ACK Failure",
                     0x21: "Network ACK Failure",
                     0x25: "Route Not Found",
                     0x74: "Payload too large",
                     0x75: "Indirect message unrequested" }[frame[5]],

                   { 0x00: "No Discovery Overhead",
                     0x02: "Route Discovery" }[frame[6]]))

        elif frame_type == 0x90:
            s += (" from %s, options 0x%x data %s" %
                  (':'.join("%x" % v for v in frame[1:9]),
                   frame[11],
                   ' '.join("%x" % v for v in frame[12:])))

        return s


    # various debugging utilities
    def t(self, which):
        self.pins[which].value(not self.pins[which].value())
        delay(1)
        self.show()

    def x(self):
        #self.show()
        self.force_spi()
        assert not self.nATTN.value(), "nATTN not asserted"
        #self.show()
        if not self.nATTN.value():
            self.nSSEL.low()
            p = self.spi.recv(6)
            assert p == b'~\x00\x02\x8a\x00u', "bad packet, got %r" % p
            assert self.nATTN.value(), "nATTN is still asserted after read"
        #self.show()

