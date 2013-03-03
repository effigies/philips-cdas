#!/usr/bin/env python
"""Interface with Philips MRI scanner through the respiration trigger

Usage:
>>> cdas = CDAS()
>>> cdas.open()
>>> cdas.trigger()
>>> cdas.close()
"""

import sys
import time
import serial
import threading


class Trigger(threading.Thread):
    """Perform action upon trigger event, optionally performing a default
    action otherwise."""
    def __init__(self, action, default=lambda: None,
                 repeat=5, tresolution=0.002, trigger=None, end=None):
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
        """Loop until signaled to end, performing default except when triggered
        to perform action"""
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
            time.sleep(nextWake - time.time())
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
            baseline = lambda: mriconn.write(
                ''.join(map(chr, [2, 130, 128, 128, 128, 128, 128, 128, 128,
                                  128, 83, 82, 48, 51, 10, 138, 13])))
        if action is None:
            action = lambda: mriconn.write(
                ''.join(map(chr, [2, 130, 128, 128, 128, 128, 128, 128, 191,
                                  255, 83, 82, 48, 51, 10, 202, 13])))

        self.mriconn = mriconn

        self.transmitter = Trigger(action, baseline)

    def trigger(self):
        """"Send 5V pulse to scanner"""
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
