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


bus = dbus.SystemBus()
hal_obj = bus.get_object("org.freedesktop.Hal", "/org/freedesktop/Hal/Manager")
hal = dbus.Interface(hal_obj, "org.freedesktop.Hal.Manager")

class Rfkill:

	def __init__(self, applet, iid):

		self.rfkill_devs = {}
		self.rfkill_devobjs = {}
		self.rfkill_names = {}
		self.rfkill_states = {}
		self.get_rfkills()
		self.get_rfstates()

		self.applet = applet
		self.tooltops = gtk.Tooltips()

		self.ebmain = gtk.EventBox()
		self.icon = gtk.Image()
		self.image = 'rfkill-applet.png'
		self.icon.set_from_file(self.image)
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
	
	def about_box(self, event, data=None):

		authors = ["Norbert Preining <preining at logic.at>"]
                about = gtk.AboutDialog()

                about.set_name("Rfkill Applet")
                about.set_version("0.1")
                about.set_copyright("(C) 2009 Norbert Preining")
                about.set_authors(authors)
                #about.set_website("nothing here for now")
                #about.set_website_label("nothing here for now")

                about.run()
                about.destroy()


	def prefs(self, event, data=None):
		print ("Not implemented")


	def click_menu(self, widget, event):
		
		if event.button == 1:
			popmenu = gtk.Menu()

			for uri in self.rfkill_names.keys():
				menu_item = gtk.CheckMenuItem(label= self.rfkill_names[uri])
				menu_item.set_active(self.rfkill_states[uri])
				menu_item.show()
				menu_item.connect("toggled", self.toggle_rfkill, uri)
				popmenu.append(menu_item)

			popmenu.show()
			popmenu.popup(None, None, None, event.button, event.time)
	
	def toggle_rfkill (self, widget, uri):
		print "Toggling " + self.rfkill_names[uri]
		dev = dbus.Interface(self.rfkill_devobjs[uri], 'org.freedesktop.Hal.Device.KillSwitch')
		newval = not(self.rfkill_states[uri])
		dev.SetPower(newval)
		self.get_rfkills()
		self.get_rfstates()
	
	def get_rfkills(self):
		self.rfkill_devobjs = {}
		self.rfkill_devs = {}
		self.rfkill_names = {}
		for udi in hal.FindDeviceByCapability ("killswitch"):
			dev_obj = bus.get_object('org.freedesktop.Hal', udi)
			dev = dbus.Interface(dev_obj, 'org.freedesktop.Hal.Device')
			if (dev.GetProperty('killswitch.type') != "unknown"):
				self.rfkill_devobjs[udi] = dev_obj
				self.rfkill_devs[udi] = dev
				self.rfkill_names[udi] = dev.GetProperty ('killswitch.name')

	def get_rfstates(self):
		for udi in self.rfkill_devs.keys():
			if (int(self.rfkill_devs[udi].GetProperty('killswitch.state')) > 0):
				self.rfkill_states[udi] = True
			else:
				self.rfkill_states[udi] = False

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

