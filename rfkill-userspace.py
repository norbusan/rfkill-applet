#!/usr/bin/env python
#
# rfkill-applet
# (C) 2009 Norbert Preining
# Licensed under GPLv3 or any version higher
#

import sys
import os
import select
import struct

print('Hello World')

event_format = "IBBBB"

fd = os.open("/dev/rfkill", os.O_RDONLY)

p = select.poll()

p.register(fd, select.POLLIN | select.POLLHUP)

while True:
  n = p.poll()
  if (n[0]):
    if (n[0][0] == fd):
      t = n[0][1]
      if (t == select.POLLIN):
        buf = os.read(fd, 8)
        if (len(buf) != 8):
          print "cannot read full event from fd"
        else:
          (idx, type, op, soft, hard) = struct.unpack(event_format, buf)
          print "RFKILL event: idx", idx, "type", type, "op", op, "soft", soft, "hard", hard
      elif (t == select.POLLHUP):
        print "pollhup event"
      else:
        print "unknown event"

# vim:set tabstop=2 expandtab: #
