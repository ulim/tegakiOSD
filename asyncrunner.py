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
import gobject

# Run asyncfunc outside and asyncfunc within the gtk event thread
class AsyncRunner(Thread):
    def __init__(self,asyncfunc,syncfunc,inval):
        Thread.__init__(self)
        self.asyncfunc = asyncfunc
        self.syncfunc = syncfunc
        self.inval = inval

    def run(self):
        ret = self.asyncfunc(self.inval)
        gobject.idle_add(self.syncfunc,ret)
