#!/usr/bin/env python

# rfkill-sys.py
# (c) 2009 Andreas Boehler, andy (dot) boehler (at) gmx (dot) at
# heavily based on rfkill-applet.py by Norbert Preining, 
# 
# This program is OpenSource, licensed under GPLv3 or any later version
#
# Changelog:
#
# v0.1, 2009/11/02
# Initial version, in fact rfkill-applet with changed GUI

# Bugs/Todo:
# In /dev/rfkill-mode, the initial status is uknown!

import pygtk
import gtk
import gobject
import os
import struct
import dbus
import time

event_format = "IBBBB"

version='0.1'

RFKILL_OP_ADD = 0
RFKILL_OP_DEL = 1
RFKILL_OP_CHANGE = 2
RFKILL_OP_CHANGE_ALL = 3

class RfkillAccess():
    AccessO = None

    def __init__ (self, applet, ignore):
        self.applet = applet
        self.rfkill_names = dict()
        self.rfkill_hardstates = dict()
        self.rfkill_softstates = dict()
        try:
            f = os.open("/dev/rfkill", os.O_RDWR)
            os.close(f)
            self.AccessO = RfkillAccessDevRfkill(applet, ignore)
            print "Using /dev/rfkill access mode"

        except:
            self.AccessO = RfkillAccessDbus(applet, ignore)
            print "Using Hal/DBUS access mode"

    def get_state (self, idx):
        return self.AccessO.get_state(idx)

    def toggle_softstate (self, idx):
        return self.AccessO.toggle_softstate (idx)

    def get_rfkillall (self):
        return self.AccessO.get_rfkillall()


class RfkillAccessDbus():
    def __init__ (self, applet, ignore):
        self.applet = applet
        self.ignored = dict()
        for k,v in ignore.iteritems():
            if v:
                self.ignored[k] = 1
        self.bus = dbus.SystemBus()
        self.hal_obj = self.bus.get_object("org.freedesktop.Hal", "/org/freedesktop/Hal/Manager")
        self.hal = dbus.Interface(self.hal_obj, "org.freedesktop.Hal.Manager")
        self.rfkill_names = dict()
        self.rfkill_hardstate = dict()
        self.rfkill_softstate = dict()
        # set up timeout for restarting
        gobject.timeout_add(3000, self.periodic_check)
        
    def periodic_check (self):
        self.parent_set_hard_switch()
        return True

    def parent_set_hard_switch (self):
        # will only be called in HAL/DBUS mode
        # we have to check for the actual hard switches
        saved_hard = self.rfkill_hardstate
        allrf = self.get_rfkillall()
        is_hard_off = False
        for idx, name in self.get_rfkillall().iteritems():
            if not(name in self.ignored):
                newhard, newsoft = self.get_state(idx)
                if newhard:
                    is_hard_off = True
        self.applet.set_hard_switch(is_hard_off)
      
    def get_rfkillall (self):
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
        dev = dbus.Interface(self.rfkill_devs[idx], 'org.freedesktop.Hal.Device.KillSwitch')
        # the value is already inverted, so no need for not
        dev.SetPower(self.rfkill_softstate[idx])

class RfkillAccessDevRfkill():
    def __init__(self, applet, ignore):
        self.ignored = dict()
        self.applet = applet
        for k,v in ignore.iteritems():
            if v:
                self.ignored[k] = 1
        self.rfkillfd = os.open("/dev/rfkill", os.O_RDONLY)
        gobject.io_add_watch(self.rfkillfd, gobject.IO_IN, self.callback_event)
        self.rfkill_names = dict()
        self.rfkill_hardstate = dict()
        self.rfkill_softstate = dict()

    def callback_event (self, fd, condition):
        buf = os.read(self.rfkillfd, 8)
        if (len(buf) != 8):
            print "cannot read full event from fd"
        else:
            (idx, type, op, soft, hard) = struct.unpack(event_format, buf)
        if op == RFKILL_OP_DEL:
            if (idx in self.rfkill_names):
                del self.rfkill_names[idx]
            return True
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

        return True

    def parent_set_hard_switch (self):
        return None
      
    def get_rfkillall (self):
        return (self.rfkill_names)
 
    def get_state (self, idx):
        if self.rfkill_names[idx]:
            return(self.rfkill_hardstate[idx], self.rfkill_softstate[idx])
        else:
            return None

    def toggle_softstate (self, idx):
        buf = struct.pack(event_format, idx, 0, RFKILL_OP_CHANGE, 
                      not(self.rfkill_softstate[idx]), 0)
        writefd = os.open("/dev/rfkill", os.O_RDWR)
        if (os.write(writefd, buf) < 8):
            print "Cannot write to rfkill the full event type"
        os.close(writefd)


class TrayMenu(object):

    def __init__(self):
        self.config_ignore = {}
        self.config_names = {}
        self.config_ignore = {}
        self.configfile = os.environ.get('HOME') + '/.rfkill-applet.config'
        self.read_config('/etc/rfkill-applet.config')
        self.read_config(self.configfile) 
        self.Access0 = RfkillAccess(self, self.config_ignore)
        self.update_all()
        
    def read_config(self, file):
        try:
            cfg = open(file, 'r')
            cfgdata = cfg.readlines()
            cfg.close()
        except:
            return

        for line in cfgdata:
            if (line.lstrip().startswith('#')):
                continue
            if line.strip() == '':
                continue
            key, val = line.strip().split('=',1)
            if val != '':
                rf,prop = key.split('.',1)
                if prop == 'onvalue':
                    self.onvalue[rf] = int(val)
                elif prop == 'offvalue':
                    self.offvalue[rf] = int(val)
                elif prop == 'ignore':
                    self.config_ignore[rf] = val
                elif prop == 'name':
                    self.config_names[rf] = val
                else:
                    print "Unkown key in config file: " + line

    def update_all(self):
        self.rfkills_hard = []
        self.rfkills_soft = []
        self.rfkills_name = []
        self.rfkills_idx = []
        self.rfkills_showname = []
        self.hardswitchedoff = False
        for idx, name in self.Access0.get_rfkillall().iteritems():
            hard, soft = self.Access0.get_state(idx)
            if hard:
                self.hardswitchedoff = True
                self.set_hard_switch(True)
            self.rfkills_hard.append(hard)
            self.rfkills_soft.append(soft)
            self.rfkills_name.append(name)
            self.rfkills_idx.append(idx)
            if (name in self.config_names):
               self.rfkills_showname.append(self.config_names[name])
            else:
                self.rfkills_showname.append(name)        
        
    def quit_activate(self, widget):
        gtk.main_quit()
        
    def set_hard_switch (self, newstate):
        self.hardswitchedoff = newstate
        if not newstate:
            icon.set_from_icon_name('rfkill-applet')
            icon.set_tooltip('Change RfKill Status')
        else:
            icon.set_from_icon_name('rfkill-applet-hardoff')  
            icon.set_tooltip('Hardware RfKill Switch is active!')
        
    def show_menu(self, widget, button, time):
        menu = gtk.Menu()
        self.update_all()
        if not self.hardswitchedoff:
            for idx,showname in enumerate(self.rfkills_showname):
                item = gtk.CheckMenuItem(label=showname)
                item.set_active(not(self.rfkills_soft[idx]))
                item.connect('activate', self.toggle_rfkill, idx)
                menu.append(item)
        item = gtk.ImageMenuItem(stock_id=gtk.STOCK_QUIT)
        item.connect('activate', self.quit_activate)
        menu.append(item)                
        menu.show_all()
        menu.popup(None, None, gtk.status_icon_position_menu, button, time, icon)
            
    def toggle_rfkill(self, widget, idx):
        self.Access0.toggle_softstate(self.rfkills_idx[idx])


icon = gtk.status_icon_new_from_icon_name('rfkill-applet')
icon.set_tooltip('RfKill')
menu = TrayMenu()
icon.connect('popup-menu', menu.show_menu)
#icon.connect('activate', menu.show_menu) # Does not work, because not enough arguments are emitted

gtk.main()
