import unittest

import random
import select
import socket
import sys
import time

from packet_buffer import PacketBuffer, ChecksumError

class TimedOutError(Exception):
    pass

class PacketBufferTestCase(unittest.TestCase):

    def setUp(self):
        self.pb = PacketBuffer()
    
    def tearDown(self):
        pass

    def testEmptyException(self):
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()

    def testOnePacket(self):
        self.pb.include_bytes(b'foobar~\x00\x02\x8a\x00u\xff\xff\xff\xff\xff\xff')
        self.assertEqual(self.pb.dequeue_one(), b'\x8a\x00')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()

    def testTwoPackets(self):
        self.pb.include_bytes(b'some random stuff then ' +
                              b'~\x00\x02\x8a\x00u' +
                              b'\xff\xff\xff\xff\xff\xff' +
                              b'~\x00\x05\x88\x03PL\x00\xd8' +
                              b'\x00\x00\x00')
        self.assertEqual(self.pb.dequeue_one(), b'\x8a\x00')
        self.assertEqual(self.pb.dequeue_one(), b'\x88\x03PL\x00')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()

    def testTwoPacketsIter(self):
        self.pb.include_bytes(b'some random stuff then ' +
                              b'~\x00\x02\x8a\x00u' +
                              b'\xff\xff\xff\xff\xff\xff' +
                              b'~\x00\x05\x88\x03PL\x00\xd8' +
                              b'\x00\x00\x00')
        self.assertEqual(list(self.pb), [b'\x8a\x00', b'\x88\x03PL\x00'])
        self.assertEqual(self.pb.dequeue_one(), b'\x8a\x00')
        self.assertEqual(self.pb.dequeue_one(), b'\x88\x03PL\x00')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()

    def testTwoPacketsOneByteAtATime(self):
        rx = b'some random stuff then ' + \
             b'~\x00\x02\x8a\x00u' + \
             b'\xff\xff\xff\xff\xff\xff' + \
             b'~\x00\x05\x88\x03PL\x00\xd8' + \
             b'\x00\x00\x00'
        for v in rx:
            self.pb.include_bytes(bytes([v]))
        self.assertEqual(len(self.pb), 2)
        self.assertEqual(self.pb.dequeue_one(), b'\x8a\x00')
        self.assertEqual(len(self.pb), 1)
        self.assertEqual(self.pb.dequeue_one(), b'\x88\x03PL\x00')
        self.assertEqual(len(self.pb), 0)
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()

    def testTwoPacketsPieces(self):
        self.pb.include_bytes(b'some random stuff then ')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()
        self.pb.include_bytes(b'~\x00\x02')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()
        self.pb.include_bytes(b'\x8a\x00u')
        self.assertEqual(self.pb.dequeue_one(), b'\x8a\x00')
        self.pb.include_bytes(b'\xff\xff\xff\xff\xff\xff')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()
        self.pb.include_bytes(b'~\x00\x05\x88\x03PL\x00')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()
        self.pb.include_bytes(b'\xd8')
        self.assertEqual(self.pb.dequeue_one(), b'\x88\x03PL\x00')
        self.pb.include_bytes(b'\x00\x00\x00')
        with self.assertRaises(IndexError):
            self.pb.dequeue_one()

    def testChecksumError(self):
        with self.assertRaises(ChecksumError):
            self.pb.include_bytes(b'foobar~\x00\x02\x8a\x01u\xff\xff\xff\xff\xff\xff')

    def testInAPacket(self):
        self.assertFalse(self.pb.in_a_packet())
        self.pb.include_bytes(b'some random stuff then ')
        self.assertFalse(self.pb.in_a_packet())
        self.pb.include_bytes(b'~\x00\x02')
        self.assertTrue(self.pb.in_a_packet())
        self.pb.include_bytes(b'\x8a\x00u')
        self.assertFalse(self.pb.in_a_packet())
        self.pb.include_bytes(b'\xff\xff\xff\xff\xff\xff')
        self.assertFalse(self.pb.in_a_packet())
        self.pb.include_bytes(b'~\x00\x05\x88\x03PL\x00')
        self.assertTrue(self.pb.in_a_packet())
        self.pb.include_bytes(b'\xd8')
        self.assertFalse(self.pb.in_a_packet())
        self.pb.include_bytes(b'\x00\x00\x00')
        self.assertFalse(self.pb.in_a_packet())
        

    def testCounters(self):
        self.assertEqual(self.pb.total_marking_bytes_count, 0)
        self.assertEqual(self.pb.marking_bytes_count, 0)
        self.assertEqual(self.pb.packet_count, 0)
        #
        self.pb.include_bytes(b'some random stuff then ')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then '))
        self.assertEqual(self.pb.marking_bytes_count,
                         len(b'some random stuff then '))
        self.assertEqual(self.pb.packet_count, 0)
        #
        self.pb.include_bytes(b'~\x00\x02')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then '))
        self.assertEqual(self.pb.marking_bytes_count, 0)
        self.assertEqual(self.pb.packet_count, 0)
        #
        self.pb.include_bytes(b'\x8a\x00')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then '))
        self.assertEqual(self.pb.marking_bytes_count, 0)
        self.assertEqual(self.pb.packet_count, 0)
        #
        self.pb.include_bytes(b'u')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then '))
        self.assertEqual(self.pb.marking_bytes_count, 0)
        self.assertEqual(self.pb.packet_count, 1)
        #
        self.pb.include_bytes(b'\xff\xff\xff\xff\xff\xff')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then ')
                         + len(b'\xff\xff\xff\xff\xff\xff'))
        self.assertEqual(self.pb.marking_bytes_count,
                         len(b'\xff\xff\xff\xff\xff\xff'))
        self.assertEqual(self.pb.packet_count, 1)
        #
        self.pb.include_bytes(b'~\x00\x05\x88\x03PL\x00')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then ')
                         + len(b'\xff\xff\xff\xff\xff\xff'))
        self.assertEqual(self.pb.marking_bytes_count, 0)
        self.assertEqual(self.pb.packet_count, 1)
        #
        self.pb.include_bytes(b'\xd8')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then ')
                         + len(b'\xff\xff\xff\xff\xff\xff'))
        self.assertEqual(self.pb.marking_bytes_count, 0)
        self.assertEqual(self.pb.packet_count, 2)
        #
        self.pb.include_bytes(b'\x00\x00\x00')
        self.assertEqual(self.pb.total_marking_bytes_count,
                         len(b'some random stuff then ')
                         + len(b'\xff\xff\xff\xff\xff\xff')
                         + len(b'\x00\x00\x00'))
        self.assertEqual(self.pb.marking_bytes_count,
                         len(b'\x00\x00\x00'))
        self.assertEqual(self.pb.packet_count, 2)






def main():
    unittest.main()

if __name__ == '__main__':
    main()
