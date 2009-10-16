#!/usr/bin/env python
#
# rfkill-client
# (C) 2009 Norbert Preining
# Licensed under GPLv3 or any version higher
#
# This is the thread that reads the rfkill device and caches the current
# status
#

import sys
import os
import threading
import select
import struct
import dbus
import time

event_format = "IBBBB"

RFKILL_OP_ADD = 0
RFKILL_OP_DEL = 1
RFKILL_OP_CHANGE = 2
RFKILL_OP_CHANGE_ALL = 3

class RfkillClient(threading.Thread):
  rfkillfd = None
  PollObj = None
  die = False

  def __init__(self, applet, ignore):

    super(RfkillClient, self).__init__()
    self.applet = applet
    self.devrfkill_works = False
    self.ignored = dict()
    for k,v in ignore.iteritems():
      if v:
        self.ignored[k] = 1

    try:
      f = os.open("/dev/rfkill", os.O_RDWR)
      self.devrfkill_works = True
      os.close(f)
      self.rfkillfd = os.open("/dev/rfkill", os.O_RDONLY)
      print "Using /dev/rfkill access mode"

    except:
      self.devrfkill_works = False
      print "Using Hal/DBUS access mode"

    if self.devrfkill_works:
      self.PollObj = select.poll()
      self.PollObj.register(self.rfkillfd, select.POLLIN | select.POLLHUP)
      self.die = False
    else:
      # why does this not work here? Why is it impossible to load
      # on demand?
      # import dbus
      self.bus = dbus.SystemBus()
      self.hal_obj = self.bus.get_object("org.freedesktop.Hal", "/org/freedesktop/Hal/Manager")
      self.hal = dbus.Interface(self.hal_obj, "org.freedesktop.Hal.Manager")


    self.rfkill_names = dict()
    self.rfkill_hardstate = dict()
    self.rfkill_softstate = dict()

  def run (self):
    
    if not(self.devrfkill_works):
      while self.die == False:
        # HAL/DBUS we wake up periodically and inform parent on the state
        time.sleep(3)
        self.parent_set_hard_switch()
    else:
      while self.die == False:
        n = self.PollObj.poll()
        if (n[0]):
          if (n[0][0] == self.rfkillfd):
            t = n[0][1]
            if (t == select.POLLIN):
              buf = os.read(self.rfkillfd, 8)
              if (len(buf) != 8):
                print "cannot read full event from fd"
              else:
                (idx, type, op, soft, hard) = struct.unpack(event_format, buf)
                if op == RFKILL_OP_DEL:
                  if (idx in self.rfkill_names):
                    del self.rfkill_names[idx]
                  continue
                  next
                if op == RFKILL_OP_ADD:
                  # name should be set from /sys/class/rfkill/rfkill%N/name
                  f = open("/sys/class/rfkill/rfkill" + str(idx) + "/name")
                  name = f.readline().rstrip()
                  f.close()
                  if not(name in self.ignored):
                    self.rfkill_names[idx] = name

                if (idx in self.rfkill_names):
                  # otherwise the rfkill switch is ignored

                  # we want to check whether a hard switch was toggled
                  # this is done by checking whether the property hard has
                  # changed
                  if (idx in self.rfkill_hardstate):
                    if (hard != self.rfkill_hardstate[idx]):
                      # inform parent that we have a hard switch toggle
                      self.applet.set_hard_switch(hard)
                  self.rfkill_hardstate[idx] = hard
                  self.rfkill_softstate[idx] = soft

            #elif (t == select.POLLHUP):
              # no idea what we can do here, or should do here
              # print "pollhup event"
            else:
              print "unknown event"

  def parent_set_hard_switch (self):
    # will only be called in HAL/DBUS mode
    # we have to check for the actual hard switches
    saved_hard = self.rfkill_hardstate
    allrf = self.get_rfkillall
    is_hard_off = False
    for idx, name in self.get_rfkillall().iteritems():
      if not(name in self.ignored):
        newhard, newsoft = self.get_state(idx)
        if newhard:
          is_hard_off = True
    self.applet.set_hard_switch(is_hard_off)
      

  def get_rfkillall (self):
    if not(self.devrfkill_works):
      # the HAL case, so nothing initialized already
      # we need to wade through the HAL stuff
      self.rfkill_names = dict()
      self.rfkill_hardstate = dict()
      self.rfkill_softstate = dict()
      self.rfkill_devs = dict()
      for udi in self.hal.FindDeviceByCapability ("killswitch"):
        dev_obj = self.bus.get_object('org.freedesktop.Hal', udi)
        dev = dbus.Interface(dev_obj, 'org.freedesktop.Hal.Device')
        if (dev.GetProperty('killswitch.type') != "unknown"):
          name = str(dev.GetProperty ('killswitch.name'))
          if (name in self.ignored):
            continue
          self.rfkill_names[udi] = name
          val = int(dev.GetProperty ('killswitch.state'))
          self.rfkill_devs[udi] = dev_obj
          if (val == 1):
            self.rfkill_hardstate[udi] = 0
            self.rfkill_softstate[udi] = 0
          elif (val == 2):
            self.rfkill_softstate[udi] = 0
            self.rfkill_hardstate[udi] = 1
          else:
            self.rfkill_softstate[udi] = 1
            self.rfkill_hardstate[udi] = 0
    return (self.rfkill_names)
 
  def get_state (self, idx):
    if self.rfkill_names[idx]:
      return(self.rfkill_hardstate[idx], self.rfkill_softstate[idx])
    else:
      return None

  def toggle_softstate (self, idx):
    if (self.devrfkill_works):
      buf = struct.pack(event_format, idx, 0, RFKILL_OP_CHANGE, 
                        not(self.rfkill_softstate[idx]), 0)
      writefd = os.open("/dev/rfkill", os.O_RDWR)
      if (os.write(writefd, buf) < 8):
        print "Cannot write to rfkill the full event type"
      os.close(writefd)
    else:
      dev = dbus.Interface(self.rfkill_devs[idx], 'org.freedesktop.Hal.Device.KillSwitch')
      # the value is already inverted, so no need for not
      dev.SetPower(self.rfkill_softstate[idx])

 
  def kill(self):
    self.die = True


# vim:set tabstop=2 expandtab: #
