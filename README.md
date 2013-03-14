philips-cdas
============

Python interface to Philips MRI scanner using the peripheral physiology
unit (PPU) signal to manually or programmatically trigger scans

## Low-level Documentation
In order to construct this, we had access to a pretty verbose MATLAB file,
which did much more than we needed and not quite what we wanted, so the
following is simply documentation of the information we gleaned. Most of this
information is in the code itself, but occasionally English allows for greater
clarity.

### Serial connection
We connect to the CDAS with baudrate 115200, no parity checking, one
stop bit, and using software flow control.

This project assumes a Linux machine with a USB-to-serial adapter that
registers as /dev/ttyUSB0. Modify the port argument in the following pyserial
invocation if these assumptions are invalid.

    serial.Serial(port='/dev/ttyUSB0',
                  baudrate=115200,
                  parity=serial.PARITY_NONE,
                  stopbits=1,
                  xonxoff=True)

### Packet definition
CDAS accepts "physiology data packets", which take the general form
`[SOM][DATA][CKSUM][EOM]`, where `SOM` is the start-of-message byte `'\x02'`,
EOM is the end-of-message byte `'\x0d'`, `DATA` is a string which will be
described presently, and `CKSUM` is simply bitwise xor of all bytes in the
`DATA` string.

#### Data string
`DATA` strings can have the following four forms:

    ['\x80'][Vx][Vx][Vy][Vy][STRING]
    ['\x81'][Vx][Vx][Vy][Vy][Vz][Vz][STRING]
    ['\x82'][Vx][Vx][Vy][Vy][PP][PP][RESP][RESP][STRING]
    ['\x83'][Vx][Vx][Vy][Vy][Vz][Vz][PP][PP][RESP][RESP][STRING]

The first field is an `ID` field, indicating which of the four strings is
being sent. `Vx`, `Vy`, `Vz`, `PP`, and `RESP` are voltage fields. Each byte
must have a 1 in their most significant bit, leaving 14 bits of flexibility.
A 0V signal is thus `'\x80\x80'`, and ±5V are `'\xbf\xff'` and `'\xff\xff'`,
respectively.

`STRING` is a variable-length status message, which appears to take the form
`'S[SIGNAL]0[MODE]\n'`. `SIGNAL` is one of `V`, `S`, `R`, `C` and `M`,
corresponding to the `V{x,y,z}`, `PP`, `RESP` signals, as well as nurse call
and `MEB`. `MODE` can be 0 for normal, 1 for connected or 3 for active. We
strictly use the string `'SS03\n'`.

#### Packets
In this signal, we have two packets, corresponding to rest and triggering.
The rest packet sends 0V along all channels, and thus looks like (spaces are
shown for field alignment, and should not appear in a packet):

    [SOM][                      DATA                      ][CKSUM][EOM]
         [ ID ][Vx][Vx][Vy][Vy][PP][PP][RESP][RESP][STRING]
    \x02  \x82 \x80\x80\x80\x80\x80\x80 \x80  \x80  SS03\n  \xcb  \x0d

The triggering packet sends 5V along the PPU channel, and looks like:

    [SOM][                      DATA                      ][CKSUM][EOM]
         [ ID ][Vx][Vx][Vy][Vy][PP][PP][RESP][RESP][STRING]
    \x02  \x82 \x80\x80\x80\x80\xbf\xff \x80  \x80  SS03\n  \x8b  \x0d
    
