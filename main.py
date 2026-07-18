#!/usr/bin/env python3
"""DevWise — GTK Git GUI for Linux"""
import sys
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ui.main_window import MainWindow

def main():
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)

    # Ctrl+Q to quit
    win.connect("key-press-event", lambda w, e: (
        Gtk.main_quit() or True
        if (e.state & __import__("gi.repository", fromlist=["Gdk"]).Gdk.ModifierType.CONTROL_MASK
            and e.keyval == __import__("gi.repository", fromlist=["Gdk"]).Gdk.KEY_q)
        else False
    ))

    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()