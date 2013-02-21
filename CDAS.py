#!/usr/bin/env python
"""Interface with Philips MRI scanner through the respiration trigger

Usage:
>>> cdas = CDAS()
>>> cdas.open()
>>> cdas.trigger()
>>> cdas.close()
"""

import time
import serial
import threading


class Trigger(threading.Thread):
    """Perform action upon trigger event, optionally performing a default
    action otherwise."""
    def __init__(self, action, default=lambda: None,
                 repeat=5, tresolution=0.002,
                 trigger=threading.Event(), end=threading.Event()):
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
        while not self.end.isSet():
            if self.trigger.isSet():
                self.action()
                if not counter:
                    print "ON!"
                counter += 1
                if counter > self.repeat:
                    print "OFF!"
                    self.trigger.clear()
                    counter = 0
            else:
                self.default()
            time.sleep(self.tresolution)

    def terminate(self):
        """End thread main loop"""
        self.end.set()


class CDAS(object):
    """Interface with Philips MRI scanner over serial, using respiration
    trigger. Send 0V ever 2ms; on trigger send 0.01ms of 5V signal.
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
        
        WARNING: If you do not close, the program may hang as the
        transmission thread does not terminate"""
        self.transmitter.terminate()
        self.mriconn.close()

    def testWithDelays(self, *ts):
        """Test timing of trigger with list of delays"""
        self.trigger()
        for t in ts:
            time.sleep(t)
            self.trigger()
