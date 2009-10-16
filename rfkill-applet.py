#!/usr/bin/env python
#
# rfkill-applet
# (C) 2009 Norbert Preining
# Licensed under GPLv3 or any version higher
#

import sys
import os
import pygtk
pygtk.require('2.0')
import threading
import gtk
import gnomeapplet

import rfkillclient

version = '0.5'

class Rfkill:

  thread = None

  def __init__(self, applet, iid):

    self.configfile = os.environ.get('HOME') + '/.rfkill-applet.config'
    self.image = '/usr/share/pixmaps/rfkill-applet.png'
    self.imagehardoff = '/usr/share/pixmaps/rfkill-applet-hardoff.png'
    self.icon_hardon = gtk.Image()
    self.icon_hardon.set_from_file(self.image)
    self.icon_hardoff = gtk.Image()
    self.icon_hardoff.set_from_file(self.imagehardoff)

    self.config_names = {}
    self.config_ignore = {}

    self.rfkills_hard = []
    self.rfkills_soft = []
    self.rfkills_name = []
    self.rfkills_showname = []
    self.hardswitchedoff = False

    self.panel_size = 24

    self.applet = applet
    self.tooltips = gtk.Tooltips()

    # read first the global config file, then a local one
    self.read_config('/etc/rfkill-applet.config')
    self.read_config(self.configfile)

    self.ebmain = gtk.EventBox()
    self.icon = gtk.Image()
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


    # start the thread that reads/writes to /dev/rfkill
    if self.thread != None:
      self.thread.kill()
      self.thread = None
    self.thread = rfkillclient.RfkillClient(self, self.config_ignore)
    self.thread.start()

    # read all data from the rfkill thread and initialize the lists
    self.update_all()

    applet.show_all()
    gtk.gdk.threads_init()
    # self.load_prefs()
  
  def update_all(self):
    self.rfkills_hard = []
    self.rfkills_soft = []
    self.rfkills_name = []
    self.rfkills_idx = []
    self.rfkills_showname = []
    self.hardswitchedoff = False
    if self.thread != None:
      for idx, name in self.thread.get_rfkillall().iteritems():
        hard, soft = self.thread.get_state(idx)
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
      for idx,showname in enumerate(self.rfkills_showname):
        menu_item = gtk.CheckMenuItem(label=showname)
        menu_item.set_active(not(self.rfkills_soft[idx]))
        menu_item.show()
        menu_item.connect("toggled", self.toggle_rfkill, idx)
        popmenu.append(menu_item)
      popmenu.show()
      popmenu.popup(None, None, None, event.button, event.time)


  def set_hard_switch (self, newstate):
    self.hardswitchedoff = newstate
    self.set_main_icon()
    self.update_tooltip()

  def toggle_rfkill (self, widget, idx):
    self.thread.toggle_softstate(self.rfkills_idx[idx])
  
  def cleanup(self, a, b):
    self.thread.kill()
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
