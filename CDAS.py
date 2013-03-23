#!/usr/bin/env python
"""Interface with Philips MRI scanner through the PPU trigger

Usage:
>>> cdas = CDAS()
>>> cdas.open()
>>> cdas.trigger()
>>> cdas.close()
"""

import sys
import time
import serial
import operator
import threading

SOM = '\x02'    # Start of message
EOM = '\x0d'    # End of message

# 14 bit two's complement integer bounds
INT14_MAX = 8191
INT14_MIN = -8192

# Status strings
ECGN = 'SV00\n'
ECGC = 'SV01\n'
ECGA = 'SV03\n'
PPUN = 'SS00\n'
PPUC = 'SS01\n'
PPUA = 'SS03\n'
RESPN = 'SR00\n'
RESPC = 'SR01\n'
RESPA = 'SR03\n'


def toByteString(val):
    """Encode 14-bit integer in two bytes where the first bit of each byte is
    1"""
    assert val >= -8192 and val <= 8191
    return chr(0x80 + ((val >> 7) & 0x7f)) + chr(0x80 + (val & 0x7f))


def checkSum(data):
    """Bitwise XOR all bytes in data"""
    cksum = reduce(operator.xor, map(ord, data))

    # Special characters (SOM, EOM, XON, XOFF) are invalid, so take one's
    # complement
    if cksum in (0x02, 0x0d, 0x11, 0x13):
        cksum = ~cksum & 0xff

    return chr(cksum)


def constructPacket(ptype='\x82', ecgx=0, ecgy=0, ecgz=0, ppu=0, resp=0,
                    status=PPUA):
    r"""Construct a packet that can be sent to a CDAS unit

    Parameters
        char    ptype   - Character indicating packet type
        int     ecgx    - ECG X voltage (Range: -8191 to 8191)
        int     ecgy    - ECG Y voltage (Range: -8191 to 8191)
        int     ecgz    - ECG Z voltage (Range: -8191 to 8191)
        int     ppu     - PPU voltage (Range: -8191 to 8191)
        int     resp    - RESP voltage (Range: -8191 to 8191)
        string  status  - Status message

    Returns
        string  packet

    The default parameters produce a PPU active packet with all zero
    fields.

    The structure of the packets is as follows:

    [SOM][              DATA              ][CKSUM][EOM]
         [ID][Vx][Vy][Vz][PP][RESP][STRING]

    SOM and EOM are '\x02' and '\x0D', respectively.

    ID determines the set of fields in DATA, and is one of '\x80', '\x81',
    '\x82', and '\x83'. Vx and Vy are always present. '\x81' and '\x83'
    indicate that Vz should be included. '\x82' and '\x83' indicate that
    PPU and RESP are to be included.

    Each byte in the two-byte voltage field begins with 1, so the fields
    allow 14 bits of information. Using a two's complement encoding, this
    permits values of -8192 to 8191.

    STRING takes the form 'S[SIGNAL]0[MODE]\n', where SIGNAL is V, S or R,
    corresponding to ECG, PPU and RESP, respectively, and MODE is 0, 1, or
    3, corresponding to "normal", "connected" and "active", respectively.

    Additional SIGNAL values include C and M for "nurse call" and "MEB".
    """

    vals = [ecgx, ecgy]
    if ptype in '\x81\x83':
        vals.append(ecgz)
    if ptype in '\x82\x83':
        vals.extend((ppu, resp))

    data = ptype + ''.join(toByteString(val) for val in vals) + status
    return SOM + data + checkSum(data) + EOM

ZEROPACKET = constructPacket()
MAXPPUPACKET = constructPacket(ppu=INT14_MAX)


class Trigger(threading.Thread):
    """Perform action upon trigger event, optionally performing a default
    action otherwise."""
    def __init__(self, action, default=lambda: None,
                 repeat=50, tresolution=0.002, trigger=None, end=None):
        if trigger is None:
            trigger = threading.Event()
        if end is None:
            end = threading.Event()

        self.default = default
        self.action = action
        self.repeat = repeat
        self.tresolution = tresolution
        self.trigger = trigger
        self.end = end
        super(Trigger, self).__init__()

    def run(self):
        """Loop until signaled to end, performing default except when
        triggered to perform action"""
        counter = 0
        nextWake = time.time() + self.tresolution
        while not self.end.isSet():
            if self.trigger.isSet():
                if counter == 0:
                    print "SCAN"
                self.action()
                counter += 1
                if counter > self.repeat:
                    self.trigger.clear()
                    counter = 0
            else:
                self.default()

            # Allow sleep time to vary to compensate for execution time
            # vagaries. Waking time should be evenly spaced.
            time.sleep(max(0, nextWake - time.time()))
            nextWake += self.tresolution

    def terminate(self):
        """End thread main loop"""
        self.end.set()


class CDAS(object):
    """Interface with Philips MRI scanner over serial, using respiration
    trigger. Send 0V every 2ms; on trigger send 10ms of 5V signal.
    """
    def __init__(self, mriconn=None, baseline=None, action=None):
        if mriconn is None:
            mriconn = serial.Serial(port='/dev/ttyUSB0',
                                    baudrate=115200,
                                    parity=serial.PARITY_NONE,
                                    stopbits=1,
                                    xonxoff=True)
        if baseline is None:
            baseline = lambda: mriconn.write(ZEROPACKET)
        if action is None:
            action = lambda: mriconn.write(MAXPPUPACKET)

        self.mriconn = mriconn

        self.transmitter = Trigger(action, baseline)

    def trigger(self):
        """Send 5V pulse to scanner"""
        self.transmitter.trigger.set()

    def open(self):
        """Open serial port and begin sending 0V to scanner"""
        if not self.mriconn.isOpen():
            self.mriconn.open()
        if not self.transmitter.isAlive():
            self.transmitter.start()

    def close(self):
        """End serial transmission and close connection

        Replaces transmission thread to allow reopening

        WARNING: If you do not close, the program may hang as the
        transmission thread does not terminate"""
        self.transmitter.terminate()
        time.sleep(self.transmitter.tresolution)

        self.transmitter = Trigger(self.transmitter.action,
                                   self.transmitter.default,
                                   self.transmitter.repeat,
                                   self.transmitter.tresolution)
        self.mriconn.close()

    def testWithDelays(self, delays):
        """Test timing of trigger with list of delays"""
        self.trigger()
        for delay in delays:
            time.sleep(delay)
            self.trigger()


def test(tty='/dev/ttyUSB0', *delays):
    """Send 10ms 5V pulse every 2 seconds or with manually specified delays"""
    if delays:
        delays = map(int, delays)
    else:
        delays = [2] * 100

    mriconn = serial.Serial(port=tty, baudrate=115200, stopbits=1,
                            parity=serial.PARITY_NONE, xonxoff=True)

    cdas = CDAS(mriconn)
    cdas.open()
    try:
        cdas.testWithDelays(delays)
    except KeyboardInterrupt:
        pass

    cdas.close()

if __name__ == '__main__':
    sys.exit(test(*sys.argv[1:]))
