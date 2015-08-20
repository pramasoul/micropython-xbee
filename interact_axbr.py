from ubinascii import hexlify, unhexlify

from asyncio_4pyb import new_event_loop, set_event_loop

from async_xbradio import Future, TimeoutError, \
    coroutine, sleep, wait_for

from async_xbradio import XBRadio, ATStatusError

import gc

from pyb import USB_VCP, SPI, Pin


class GotEOT(Exception):
    pass

class XBRadio_CLI():

    def __init__(self, xb, role):
        self.xb = xb
        self.role = role
        self.console = USB_VCP()
        self.command_dispatch = { }

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
        if not line:
            return

        cmd, _, rol = line.partition(b' ')
        cmd = str(cmd, 'ASCII')
        rol = rol.lstrip()

        fun = self.command_dispatch.get(cmd.lower())
        if fun:
            yield from fun(self, cmd, rol)
        elif cmd in ('help', '?'):
            yield from self.write('Commands are: ')
            yield from self.writeln(', '.join(sorted(self.command_dispatch.keys())))
        else:
            yield from self.writeln('huh?')


    @coroutine
    def repl(self, xb, noquit=False):
        xb = self.xb
        if not xb.started:
            yield from xb.start()
        console = self.console
        while(console.isconnected()):
            prompt = bytes(self.role + '> ', 'ASCII')
            #console.self.write(prompt)
            yield from self.write(prompt)
            try:
                line = yield from self.readline()
                yield from self.interpret(line)
            except GotEOT:
                if noquit:
                    yield from self.writeln("can't quit!")
                else:
                    return


################################################################

@coroutine
def info_cmd(cli, cmd, rol):

    @coroutine
    def showAT(at):
        yield from cli.write(' %s %d' % (at, (yield from cli.xb.AT_cmd(at))))

    yield from cli.write('addr %s' % hexlify(cli.xb.address))
    yield from showAT('DB')
    yield from showAT('PL')
    gc.collect()
    yield
    gc.collect()
    yield from cli.write(' mem_free %d' % gc.mem_free())
    yield from cli.writeln('')


@coroutine
def at_cmd(cli, cmd, rol):
    try:
        v = yield from cli.xb.AT_cmd(rol[:2], rol[2:])
    except ATStatusError as e:
        yield from cli.writeln(e.args[0])
    else:
        yield from cli.writeln(repr(v))

@coroutine
def echo_cmd(cli, cmd, rol):
    try:
        n = int(rol.split()[0])
    except:
        n = 1
    yield from cli.echoServer(n)

@coroutine
def rx_cmd(cli, cmd, rol):
    try:
        n = int(rol.split()[0])
    except:
        n = 1
    for i in range(n):
        a, d = yield from cli.xb.rx()
        yield from cli.writeln('from %s got %r' % \
                           (str(hexlify(a), 'ASCII'), d))

@coroutine
def tx_cmd(cli, cmd, rol):
    addr, _, payload = rol.partition(b':')
    address = unhexlify(addr)
    yield from cli.write('sending %d bytes to %r...' % \
                       (len(payload), address))
    status = yield from wait_for((yield from cli.xb.tx(payload, address)))
    yield from cli.writeln('status %r' % status)

@coroutine
def quit_cmd(cli, cmd, rol):
    raise GotEOT



@coroutine
def heyUsaid_cmd(cli, cmd, rol):
    yield from cli.writeln("You said %s %s" % (cmd, rol))


def inject_standard_commands(cli):
    cli.command_dispatch.update({
        'info': info_cmd,
        'at': at_cmd,
        'hey': heyUsaid_cmd,
        'echo': echo_cmd,
        'rx': rx_cmd,
        'tx': tx_cmd,
        'quit': quit_cmd })




def interact(role=None):

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



    if role is None:
        config = eval(open('xbradio.cfg').read())
        role = config['role']
    else:
        role = role
    xb = create_test_radio(role)
    cli = XBRadio_CLI(xb, role)

    inject_standard_commands(cli)

    loop = new_event_loop()
    set_event_loop(loop)
    loop.run_until_complete(cli.repl(xb))

if __name__ == '__main__':
    interact()
