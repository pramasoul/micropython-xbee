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

class XBRadio_CLI():

    def __init__(self, xb, role):
        self.xb = xb
        self.role = role
        self.console = USB_VCP()

    @coroutine
    def readline(self):
        console = self.console
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
    def write(self, buf):
        self.console.write(buf)
        yield

    @coroutine
    def writeln(self, buf):
        yield from self.write(buf)
        yield from self.write(b'\r\n')

    @coroutine
    def echoServer(self, n=10):
        xb = self.xb
        for i in range(n):
            a, d = yield from xb.rx()
            yield from self.writeln('echoing %r to %s' % \
                               (d, str(hexlify(a), 'ASCII')))
            yield from xb.tx(d, a)

    @coroutine
    def interpret(self, line):
        #yield from self.write(b'got "' + line + '"\r\n')
        if not line:
            return

        cmd, _, rol = line.partition(b' ')
        cmd = str(cmd, 'ASCII')
        rol = rol.lstrip()
        xb = self.xb

        def showAT(at):
            yield from self.write(' %s %d' % (at, (yield from xb.AT_cmd(at))))

        if cmd == 'info':
            yield from self.write('addr %r' % hexlify(xb.address))
            yield from showAT('DB')
            yield from showAT('PL')
            yield from self.writeln('')

        elif cmd.lower().startswith('at'):
            try:
                v = yield from xb.AT_cmd(cmd[2:4], cmd[4:])
            except ATStatusError as e:
                yield from self.writeln(e.args[0])
            else:
                yield from self.writeln(repr(v))

        elif cmd == 'echo':
            try:
                n = int(rol.split()[0])
            except:
                n = 1
            yield from echoServer(n)

        elif cmd == 'rx':
            try:
                n = int(rol.split()[0])
            except:
                n = 1
            for i in range(n):
                a, d = yield from xb.rx()
                yield from self.writeln('from %s got %r' % \
                                   (str(hexlify(a), 'ASCII'), d))

        elif cmd == 'tx':
            addr, _, payload = rol.partition(b':')
            address = unhexlify(addr)
            yield from self.write('sending %d bytes to %r...' % \
                               (len(payload), address))
            status = yield from wait_for((yield from xb.tx(payload, address)))
            yield from self.writeln('status %r' % status)

        elif cmd in ('quit', 'exit', 'bye'):
            raise GotEOT

        else:
            yield from self.writeln('huh?')


    @coroutine
    def repl(self, xb):
        xb = self.xb
        console = self.console
        yield from xb.start()
        while(console.isconnected()):
            prompt = bytes(self.role + '> ', 'ASCII')
            #console.self.write(prompt)
            yield from self.write(prompt)
            try:
                line = yield from self.readline()
                yield from self.interpret(line)
            except GotEOT:
                return


def interact(role=None):
    if role is None:
        config = eval(open('xbradio.cfg').read())
        role = config['role']
    else:
        role = role
    xb = create_test_radio(role)
    cli = XBRadio_CLI(xb, role)

    loop = new_event_loop()
    #print("role %r, console %r, xb %r, loop %r" % (role, console, xb, loop))
    set_event_loop(loop)
    loop.run_until_complete(cli.repl(xb))

if __name__ == '__main__':
    interact()
