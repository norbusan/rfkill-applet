#!/usr/bin/env python
#
# rfkill-applet
# (C) 2009 Norbert Preining
# Licensed under GPLv3 or any version higher
#

import sys
import os
import dbus
import pygtk
pygtk.require('2.0')

import gtk
import gnomeapplet

import gobject

# from dbus.mainloop.glib import DBusGMainLoop
# DBusGMainLoop(set_as_default=True)

version = '0.3'

bus = dbus.SystemBus()
hal_obj = bus.get_object("org.freedesktop.Hal", "/org/freedesktop/Hal/Manager")
hal = dbus.Interface(hal_obj, "org.freedesktop.Hal.Manager")

class Rfkill:

  def __init__(self, applet, iid):

    self.configfile = os.environ.get('HOME') + '/.rfkill-applet.config'
    self.image = '/usr/share/pixmaps/rfkill-applet.png'
    self.imagehardoff = '/usr/share/pixmaps/rfkill-applet-hardoff.png'
    self.icon_hardon = gtk.Image()
    self.icon_hardon.set_from_file(self.image)
    self.icon_hardoff = gtk.Image()
    self.icon_hardoff.set_from_file(self.imagehardoff)

    self.rfkill_devs = {}
    self.rfkill_devobjs = {}
    self.rfkill_usernames = {}
    self.rfkill_names = {}
    self.rfkill_states = {}
    self.rfkill_ignore = {}
    self.onvalue = {}
    self.offvalue = {}
    self.hardswitch = ''
    self.default_onvalue = -1
    self.default_offvalue = -1
    self.default_hardoffvalue = -1

    # that are milliseconds!
    self.timeout_interval = 3000

    self.panel_size = 24

    self.applet = applet
    self.tooltips = gtk.Tooltips()

    # read first the global config file, then a local one
    self.read_config('/etc/rfkill-applet.config')
    self.read_config(self.configfile)

    self.ebmain = gtk.EventBox()

    self.icon = gtk.Image()

    self.update_all()
    gobject.timeout_add(self.timeout_interval, self.update_all)

    self.ebmain.add(self.icon)
    self.applet.add(self.ebmain)

    self.ebmain.connect("button-press-event", self.click_menu)

    applet.connect("destroy", self.cleanup)

    self.menuxml="""
    <popup name="button3">
    <menuitem name="Item 1" verb="About" label="_About" pixtype="stock" pixname="gnome-stock-about"/>
    <menuitem name="Item 2" verb="Preferences" label="_Preferences" pixtype="stock" pixname="gtk-preferences"/>
    </popup>
    """

    self.applet.setup_menu(self.menuxml, [ ("About",self.about_box), ("Preferences",self.prefs) ], None)

    applet.show_all()
    # self.load_prefs()
  

  def update_all(self):
    self.get_rfkills()
    self.get_rfstates()
    self.set_main_icon()
    self.update_tooltip()
    # return true, otherwise the gobject timer removes that callback
    return True
    
  def update_tooltip(self):
    if (self.hardswitchedoff):
      self.tooltips.set_tip(self.ebmain, "The devices are switched off by hardware. You have to switch the hardware switch first on!")
    else:
      self.tooltips.set_tip(self.ebmain, "Click for configuration of active devices")

  def about_box(self, event, data=None):
    authors = ["Norbert Preining <preining at logic.at>"]
    about = gtk.AboutDialog()
    about.set_name("Rfkill Applet")
    about.set_version(version)
    about.set_copyright("(C) 2009 Norbert Preining")
    about.set_authors(authors)
    #about.set_website("nothing here for now")
    #about.set_website_label("nothing here for now")
    about.run()
    about.destroy()


  def prefs(self, event, data=None):
    prefdiag = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
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
      # first all the normal key=value pairs
      if key == 'default_onvalue':
        if val != '':
          self.default_onvalue = int(val)
      elif key == 'default_offvalue':
        if val != '':
          self.default_offvalue = int(val)
      elif key == 'default_hardoffvalue':
        if val != '':
          self.default_hardoffvalue = int(val);
      elif key == 'hardswitch':
        if val != '':
          self.hardswitch = val
      # now the specifications rfkill.property=val
      else:
        if val != '':
          rf,prop = key.split('.',1)
          if prop == 'onvalue':
            self.onvalue[rf] = int(val)
          elif prop == 'offvalue':
            self.offvalue[rf] = int(val)
          elif prop == 'ignore':
            self.rfkill_ignore[rf] = val
          elif prop == 'name':
            self.rfkill_usernames[rf] = val
          else:
            print "Unkown key in config file: " + line


  def set_main_icon(self):
    if (self.hardswitchedoff):
      self.icon.set_from_file(self.imagehardoff)
    else:
      self.icon.set_from_file(self.image)


  def click_menu(self, widget, event):
    if event.button == 1:
      popmenu = gtk.Menu()
      self.update_all()
      if (self.hardswitchedoff):
        return

      for uri in self.rfkill_names.keys():
        name = self.rfkill_names[uri]
        if (name in self.rfkill_usernames):
          showname = self.rfkill_usernames[name]
        else:
          showname = name
        if (self.hardswitch != name):
          menu_item = gtk.CheckMenuItem(label=showname)
          if (self.hardswitchedoff):
            self.tooltips.set_tip(menu_item, "The hardware switch is activated, you cannot use software to turn this device on.")
          menu_item.set_active(self.rfkill_states[uri])
          menu_item.show()
          menu_item.connect("toggled", self.toggle_rfkill, uri)
          popmenu.append(menu_item)
      popmenu.show()
      popmenu.popup(None, None, None, event.button, event.time)


  def toggle_rfkill (self, widget, uri):
    #print "Toggling " + self.rfkill_names[uri]
    dev = dbus.Interface(self.rfkill_devobjs[uri], 'org.freedesktop.Hal.Device.KillSwitch')
    newval = not(self.rfkill_states[uri])
    dev.SetPower(newval)
  

  def get_rfkills(self):
    self.rfkill_devobjs = {}
    self.rfkill_devs = {}
    self.rfkill_names = {}
    for udi in hal.FindDeviceByCapability ("killswitch"):
      dev_obj = bus.get_object('org.freedesktop.Hal', udi)
      dev = dbus.Interface(dev_obj, 'org.freedesktop.Hal.Device')
      if (dev.GetProperty('killswitch.type') != "unknown"):
        name = str(dev.GetProperty ('killswitch.name'))
        if (not(name in self.rfkill_ignore)):
          self.rfkill_devobjs[udi] = dev_obj
          self.rfkill_devs[udi] = dev
          self.rfkill_names[udi] = name

  def get_rfstates(self):
    # first we check if there is an hardware switch defined
    hardoffval = self.default_hardoffvalue
    if (self.hardswitch != ''):
      for udi in self.rfkill_devs.keys():
        name = self.rfkill_names[udi]
        if (self.hardswitch == name):
          if (name in self.offvalue):
            hardoffval = self.offvalue[name]

    for udi in self.rfkill_devs.keys():
      name = self.rfkill_names[udi]
      val = int(self.rfkill_devs[udi].GetProperty('killswitch.state'))

      offval = self.default_offvalue
      if (name in self.offvalue):
        offval = self.offvalue[name]

      onval  = self.default_onvalue
      if (name in self.offvalue):
        onval = self.onvalue[name]

      if (val == onval):
        self.rfkill_states[udi] = True
      elif (val == offval):
        self.rfkill_states[udi] = False
      elif (val == hardoffval):
        self.rfkill_states[udi] = False
      else:
        print "Unknown state: ", val

      if (self.hardswitch == name):
        self.hardswitchedoff = not(self.rfkill_states[udi])


  def cleanup(self, data):
    gtk.main_quit()
    sys.exit()


def rfkill_factory(applet, iid):
  Rfkill(applet, iid)
  return True

if len(sys.argv) == 2 and sys.argv[1] == '-d':   
  main_window = gtk.Window(gtk.WINDOW_TOPLEVEL)
  main_window.set_title("Rfkill Applet")
  main_window.connect("destroy", gtk.main_quit) 
  app = gnomeapplet.Applet()
  rfkill_factory(app, None)
  app.reparent(main_window)
  main_window.show_all()
  gtk.main()
  sys.exit()

if __name__ == '__main__':
  print('Starting factory')
  gnomeapplet.bonobo_factory("OAFIID:RfkillApplet_Factory", 
                             gnomeapplet.Applet.__gtype__, 
                             "RFKill Switch Applet", "0.1", 
                             rfkill_factory)

# vim:set tabstop=2 expandtab: #
