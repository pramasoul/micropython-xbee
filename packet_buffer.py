class PacketException(Exception):
    pass

class ChecksumError(PacketException):
    pass

class PacketBuffer(object):
    def __init__(self):
        self.packets = []
        self.reset_parse()
        self.total_marking_bytes_count = 0
        self.marking_bytes_count = 0
        self.packet_count = 0

    def reset_parse(self):
        self.packet_buf = b''
        # 0: looking for new packet
        # 1: found sync ('~')
        # 2: have first byte of payload length
        # 3: have payload length, gathering payload
        # 4: have full payload, need check byte
        self.state = 0

    def __len__(self):
        return len(self.packets)

    def __iter__(self):
        return iter(self.packets)

    def dequeue_one(self):
        return self.packets.pop(0)

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
                want = self.payload_length - len(self.packet_buf)
                self.packet_buf += b[:want]
                b = b[want:]
                if len(self.packet_buf) == self.payload_length:
                    self.state = 4
            if self.state is 4:
                if len(b):
                    check_byte = b[0]
                    b = b[1:]
                    if (sum(self.packet_buf) & 0xff) + check_byte != 0xff:
                        self.bad = (self.packet_buf, check_byte)
                        self.reset_parse()
                        raise ChecksumError("sum(packet) = 0x%x, check_byte = 0x%x" \
                                          % (sum(self.bad[0]), self.bad[1]))
                    self.packets.append(self.packet_buf)
                    self.packet_count += 1
                    self.packet_buf = b''
                    self.state = 0

    def in_a_packet(self):
        return bool(self.state)

# Don't optimize prematurely:
#    def bytes_needed_to_finish_next_packet(self):
#        return 0                # FIXME
