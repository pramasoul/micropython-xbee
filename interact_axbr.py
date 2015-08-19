from ubinascii import hexlify, unhexlify

from asyncio_4pyb import new_event_loop, set_event_loop

from async_xbradio import Future, TimeoutError, \
    coroutine, sleep, wait_for
    

from async_xbradio import XBRadio, ATStatusError

from pyb import USB_VCP, SPI, Pin


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
def echoServer(n=10):
    for i in range(n):
        a, d = yield from xb.rx()
        yield from writeln('echoing %r to %s' % \
                           (d, str(hexlify(a), 'ASCII')))
        yield from xb.tx(d, a)

@coroutine
def interpret(line):
    #yield from write(b'got "' + line + '"\r\n')
    if not line:
        return

    cmd, _, rol = line.partition(b' ')
    cmd = str(cmd, 'ASCII')
    rol = rol.lstrip()

    def showAT(at):
        yield from write(' %s %d' % (at, (yield from xb.AT_cmd(at))))

    if cmd == 'info':
        yield from write('addr %r' % hexlify(xb.address))
        yield from showAT('DB')
        yield from showAT('PL')
        yield from writeln('')

    elif cmd.lower().startswith('at'):
        try:
            v = yield from xb.AT_cmd(cmd[2:4], cmd[4:])
        except ATStatusError as e:
            yield from writeln(e.args[0])
        else:
            yield from writeln(repr(v))

    elif cmd == 'echo':
        try:
            n = int(rol.split()[0])
        except:
            n = 1
        yield from echoServer(n)

    elif cmd == 'rx':
        a, d = yield from xb.rx()
        yield from writeln('from %s got %r' % \
                           (str(hexlify(a), 'ASCII'), d))

    elif cmd == 'tx':
        addr, _, payload = rol.partition(b':')
        address = unhexlify(addr)
        yield from write('sending %d bytes to %r...' % \
                           (len(payload), address))
        status = yield from wait_for((yield from xb.tx(payload, address)))
        yield from writeln('status %r' % status)

    elif cmd in ('quit', 'exit', 'bye'):
        raise GotEOT

    else:
        yield from writeln('huh?')


@coroutine
def repl(xb):
    yield from xb.start()
    while(console.isconnected()):
        prompt = bytes(_role + '> ', 'ASCII')
        #console.write(prompt)
        yield from write(prompt)
        try:
            line = yield from readline()
            yield from interpret(line)
        except GotEOT:
            return


def interact(role=None):
    global _role
    if role is None:
        config = eval(open('xbradio.cfg').read())
        _role = config['role']
    else:
        _role = role

    global console
    console = USB_VCP()
    global xb
    xb = create_test_radio(role)

    loop = new_event_loop()
    #print("role %r, console %r, xb %r, loop %r" % (role, console, xb, loop))
    set_event_loop(loop)
    loop.run_until_complete(repl(xb))

if __name__ == '__main__':
    interact()
