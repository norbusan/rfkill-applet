#!/usr/bin/env python
#
# rfkill-applet
# (C) 2009, 2010, 2011, 2014 Norbert Preining
# Licensed under GPLv3 or any version higher
#

import gi

gi.require_version("Gtk", "2.0")

from gi.repository import Gtk
from gi.repository import MatePanelApplet

import sys
import os
from gi.repository import Gio
from gi.repository import GObject
import struct
import dbus
import fnmatch

version = '0.9pre'


event_format = "IBBBB"

RFKILL_OP_ADD = 0
RFKILL_OP_DEL = 1
RFKILL_OP_CHANGE = 2
RFKILL_OP_CHANGE_ALL = 3

def is_ignore_with_wildcards (what, ilist):
  for dname in ilist:
    if fnmatch.fnmatch(what, dname):
      return True
  return False

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
    GObject.timeout_add(3000, self.periodic_check)

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
      if not(is_ignore_with_wildcards(name, self.ignored)):
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
        if is_ignore_with_wildcards(name, self.ignored):
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
    GObject.io_add_watch(self.rfkillfd, GObject.IO_IN, self.callback_event)
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
        if not(is_ignore_with_wildcards(name, self.ignored)):
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
 

class SysSwitch:
  def __init__(self, applet, name, filename, onval):
    self.applet = applet
    self.fn = filename
    self.name = name
    self.onvalue = onval
    self.giof = Gio.File(path=filename)
    self.monitor = self.giof.monitor_file(Gio.FileMonitorFlags.NONE, None)
    self.monitor.connect("changed", self.callback_event)
    self.state = int(self.get_state())

  def get_sysfs_value(self):
    try:
      file_descriptor = open(self.fn)
    except:
      return ""
    value = file_descriptor.read()
    file_descriptor.close()
    return value

  def set_sysfs_value(self, value):
    try:
      file_descriptor = open(self.fn, 'w')
    except:
      print "Cannot opfen " + self.fn + " for writing!"
      return False
    file_descriptor.write("%d" % int(value))
    file_descriptor.close()
    return True

  def callback_event (self, monitor, file1, file2, evt_type):
    self.state = int(self.get_state())
    return self.state

  def get_state (self):
    return self.get_sysfs_value()

  def toggle_softstate (self, idx):
    if (self.state == 0):
      newstate = self.onvalue
    else:
      newstate = 0
    if (self.set_sysfs_value(newstate)):
      self.state = newstate
      return True
    else:
      print "Cannot write to " + self.fn
      return False

class Rfkill:
  def __init__(self, applet, iid):

    self.configfile = os.environ.get('HOME') + '/.rfkill-applet.config'
    self.image = '/usr/share/pixmaps/rfkill-applet.png'
    self.imagehardoff = '/usr/share/pixmaps/rfkill-applet-hardoff.png'
    self.icon_hardon = Gtk.Image()
    self.icon_hardon.set_from_file(self.image)
    self.icon_hardoff = Gtk.Image()
    self.icon_hardoff.set_from_file(self.imagehardoff)

    self.config_names = {}
    self.config_files = {}
    self.config_types = {}
    self.config_ignore = {}
    self.onvalue = {}

    self.rfkills_hard = []
    self.rfkills_soft = []
    self.rfkills_name = []
    self.rfkills_showname = []
    self.hardswitchedoff = False

    self.sys_kills = []

    self.panel_size = 24

    self.applet = applet

    # read first the global config file, then a local one
    self.read_config('/etc/rfkill-applet.config')
    self.read_config(self.configfile)

    self.ebmain = Gtk.EventBox()
    self.icon = Gtk.Image()
    self.ebmain.add(self.icon)
    self.applet.add(self.ebmain)
    self.ebmain.connect("button-press-event", self.click_menu)
    applet.connect("destroy", self.cleanup)

    self.menuxml="""
    <popup name="button3">
    <menuitem name="Item 1" verb="About" label="_About" pixtype="stock" pixname="gtk-about"/>
    <menuitem name="Item 2" verb="Preferences" label="_Preferences" pixtype="stock" pixname="gtk-preferences"/>
    <menuitem name="Item 3" verb="Quit" label="_Quit" pixtype="stock" pixname="gtk-quit"/>
    </popup>
    """

    self.applet.setup_menu(self.menuxml, [ ("About",self.about_box), ("Preferences",self.prefs), ("Quit", self.cleanup) ], None)


    self.AccessO = RfkillAccess(self, self.config_ignore)

    self.update_all()
  
    # support /sys files switches
    for rf,filename in self.config_files.iteritems():
      onval = 1
      if (rf in self.onvalue):
        onval = self.onvalue[rf]
      
      try:
        foo = open(filename)
      except:
        print "ignoring sys switch for " + filename
        print "file does not exist!"
        continue

      foo.close
      tmp = SysSwitch(self, rf, filename, onval)
      self.sys_kills.append(tmp)

    applet.show_all()
    # self.load_prefs()
  
  def update_all(self):
    self.rfkills_hard = []
    self.rfkills_soft = []
    self.rfkills_name = []
    self.rfkills_idx = []
    self.rfkills_showname = []
    self.hardswitchedoff = False
    for idx, name in self.AccessO.get_rfkillall().iteritems():
      hard, soft = self.AccessO.get_state(idx)
      if hard:
        self.hardswitchedoff = True
      self.rfkills_hard.append(hard)
      self.rfkills_soft.append(soft)
      self.rfkills_name.append(name)
      self.rfkills_idx.append(idx)
      if (name in self.config_names):
        self.rfkills_showname.append(self.config_names[name])
      else:
        self.rfkills_showname.append(name)
    self.set_main_icon()
    self.update_tooltip()
    
  def update_tooltip(self):
    if (self.hardswitchedoff):
      self.ebmain.set_tooltip_text( "The devices are switched off by hardware. You have to switch the hardware switch first on!")
    else:
      self.ebmain.set_tooltip_text("Click for configuration of active devices")

  def about_box(self, event, data=None):
    authors = ["Norbert Preining <preining at logic.at>"]
    about = Gtk.AboutDialog()
    about.set_name("Rfkill Applet")
    about.set_version(version)
    about.set_copyright("(C) 2009, 2010, 2011 Norbert Preining")
    about.set_authors(authors)
    #about.set_website("nothing here for now")
    #about.set_website_label("nothing here for now")
    about.run()
    about.destroy()


  def prefs(self, event, data=None):
    prefdiag = Gtk.MessageDialog(buttons=Gtk.ButtonsType.OK)
    prefdiag.set_property('text', "Not implemented yet!")
    prefdiag.run()
    prefdiag.destroy()

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
        elif prop == 'file':
          self.config_files[rf] = val
        elif prop == 'type':
          self.config_types[rf] = val
        else:
          print "Unknown key in config file: " + line


  def set_main_icon(self):
    if (self.hardswitchedoff):
      self.icon.set_from_file(self.imagehardoff)
    else:
      self.icon.set_from_file(self.image)


  def click_menu(self, widget, event):
    if event.button == 1:
      popmenu = Gtk.Menu()
      self.update_all()
      if (not(self.hardswitchedoff)):
        for idx,showname in enumerate(self.rfkills_showname):
          menu_item = Gtk.CheckMenuItem(label=showname)
          menu_item.set_active(not(self.rfkills_soft[idx]))
          menu_item.show()
          menu_item.connect("toggled", self.toggle_rfkill, idx)
          popmenu.append(menu_item)
      for idx,syskill in enumerate(self.sys_kills):
        menu_item = Gtk.CheckMenuItem(label=syskill.name)
        menu_item.set_active(int(syskill.state))
        menu_item.show()
        menu_item.connect("toggled", syskill.toggle_softstate)
        popmenu.append(menu_item)

      popmenu.show()
      popmenu.popup(None, None, None, event.button, event.time)


  def set_hard_switch (self, newstate):
    self.hardswitchedoff = newstate
    self.set_main_icon()
    self.update_tooltip()

  def toggle_rfkill (self, widget, idx):
    self.AccessO.toggle_softstate(self.rfkills_idx[idx])
  
  def cleanup(self, a, b):
    Gtk.main_quit()
    sys.exit()


def rfkill_factory(applet, iid):
  Rfkill(applet, iid)
  return True

if len(sys.argv) == 2 and sys.argv[1] == '-d':   
  main_window = Gtk.Window(Gtk.WindowType.TOPLEVEL)
  main_window.set_title("Rfkill Applet")
  main_window.connect("destroy", Gtk.main_quit) 
  app = gnomeapplet.Applet()
  rfkill_factory(app, None)
  app.reparent(main_window)
  main_window.show_all()
  Gtk.main()
  sys.exit()

if __name__ == '__main__':
  print('Starting factory')
  MatePanelApplet.Applet.factory_main("OAFIID:RfkillApplet_Factory", True,
                             MatePanelApplet.Applet.__gtype__, 
                             rfkill_factory, None)


# vim:set tabstop=2 expandtab: #
