#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009 The Tegaki project contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

# Contributors to this file:
# - Uli Meis

from threading import Thread
import xinputextdev
import gtk,gobject

gobject.threads_init()

class XInputEvent(object):
    XIE_MOVE           = 0
    XIE_BUTTON_PRESS   = 1
    XIE_BUTTON_RELEASE = 2
    XIE_PROX_IN        = 3
    XIE_PROX_OUT       = 4

    def __init__(self,info,res):
        self.time = info[0]
        self.type = info[1]
        self.x = info[2]
        self.y = info[3]
        self.button = info[4]
        self.resolution = res

class XInputHandler(Thread):
    def __init__(self,):
        Thread.__init__(self)
        self.term = False
        self.func = None
        self.devices = xinputextdev.init()
        self.setDaemon(True)

    def grab(self,devname):
        self.res = xinputextdev.grab(devname)
        if self.res==0: return
        xbordersize = (self.res[0]-self.res[1])/2
        print "xinput dev resolution %d,%d" % tuple(self.res)

    def events(self,polldata):
        for data in polldata:
                self.func(XInputEvent(data,self.res))

    def run(self):
        gtk.quit_add(0,self.termme)
        while(not self.term):
            polldata = xinputextdev.poll()
            if polldata!=[]:
                gobject.idle_add(self.events,polldata)

    def termme(self):
        self.term = True
        xinputextdev.term()
