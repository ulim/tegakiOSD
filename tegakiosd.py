#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 The Tegaki project contributors
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

VERSION = '0.1'

# General
import math,os,sys,re
from subprocess import Popen,PIPE

# UI
import gtk,cairo,gobject
from gtk import gdk
import pango
import pangocairo

# Tegaki
from tegaki.character import *
from tegaki.recognizer import Recognizer

# XInput
from xinputhandler import XInputHandler,XInputEvent

# Tool
from asyncrunner import AsyncRunner

# Tegaki On-Screen-Display class

class TegakiOSD(gtk.Window):

    USAGE = """Welcome to TegakiOSD!  This app is optimized for
a pen tablet but it's usable with a mouse as well.

Use the pen(left mouse button) to draw. After the
first stroke choices will appear in the
background. Whenever you see your desired choice
move over it and press the pen's first
button(middle mouse button) to commit. Press the
pen's second button(right mouse button) at any
time to erase.

Whenever the screen is clear you can hold down the
pen's second button and select a recognition
model.

To move the window, click on it with the mouse and
window decorations will appear. Click again and
they will vanish. If you don't have a tablet you
can activate the decorations in the model
selection menu(right mouse button).

Good Luck!"""

    DEFAULT_WIDTH = 400
    DEFAULT_HEIGHT = 400
    DEFAULT_FONT_CHAR = "KanjiStrokeOrders,Serif"
    DEFAULT_FONT_CFG = "Serif"
    # Needs to be in default platform encoding
    DEFAULT_KANJIDIC_PATH = "~/doc/jap/kanjidic"

    # poor man's kanjidic support
    KANJIDIC_CMD = """grep '^%s' %s |tr ' ' '\n'|sed -e':b;/^{[^}]*$/{N;s/\\n/ /;b b;};

/^S/{s/S/Strokes: /;b;};
/^G/{s/G/Grade: /;b;};
/^F/{s/F/Freq. Rank: /;b;};

/^{/b;/^W/,/^T/!d;/^[WT]/d'|tr -d '{}'"""


    CHAR_FAC = 0.9

    PROXOUT = 0

    # states
    ST_PROXOUT  = 0
    ST_PROXIN   = 1
    ST_DRAWING  = 2
    ST_CHOOSING = 3
    ST_TERM     = 4

    CURSOR_RADIUS = 5

    #
    # Init methods
    #

    def __init__(self,devname=None):

        self.osdstate = self.ST_PROXOUT

        # current candidates
        self.candidates = None
        # current choice
        self.choice = None
        # cursor extents
        self.csext = None
        # timestamp of last PROXOUT event
        self.lastprox = None
        # current cursor position
        self.cpos = None
        # last stroke position
        self.lastp = None
        #
        self.shown = False
        # force cursor redraw
        self.cursor_redraw = True
        # True if a recog thread is running
        self.strokes_async_running = False
        # fields per line
        self.choice_per_line = 0
        # no tablet?
        self.faking = False
        # kanjidic available?
        self.DEFAULT_KANJIDIC_PATH = os.path.expanduser(
                self.DEFAULT_KANJIDIC_PATH)
        self.have_kanjidic = os.path.exists(self.DEFAULT_KANJIDIC_PATH)
        
        self.init_xinput(devname)
        self.init_window()
        self.init_graphics()
        self.init_recog()

    # Grab device
    def init_xinput(self,devname):
        xihandler = XInputHandler()
        grabbed = False
        for i in range(0,len(xihandler.devices)):
            print "Device: %s" % xihandler.devices[i]
            if (devname and xihandler.devices[i]==devname) or (devname==None and
                    xihandler.devices[i].endswith("Pen")):
                xihandler.grab(i)
                grabbed = True
                break
        if grabbed:
            xihandler.func = self.process_input_event
            xihandler.start()
            self.xihandler = xihandler
            self.tresolution = xihandler.res
        else:
            # Fake with mouse
            self.faking = True

    # Initialize UI
    def init_window(self):
        gtk.Window.__init__(self)

        self.width = self.DEFAULT_WIDTH
        self.height = self.DEFAULT_HEIGHT

        win = self
        win.resize(self.width,self.height)
        win.set_app_paintable(True)
        win.set_decorated(False)
        win.connect('expose-event', self.expose)
        win.connect('delete-event', gtk.main_quit)
        win.connect('destroy-event', self.destroy)
        win.add_events(gdk.BUTTON_PRESS_MASK)
        win.connect('button-press-event', self.mouse_press)
        if self.faking:
            win.add_events(gdk.BUTTON_RELEASE_MASK)
            win.add_events(gdk.POINTER_MOTION_MASK)
            win.connect('button-release-event', self.mouse_release)
            win.connect('motion-notify-event', self.mouse_motion)
        win.set_accept_focus(False)
        win.set_property('skip-taskbar-hint',True)
        win.set_keep_above(True)

        screen = self.get_screen()
        colormap = screen.get_rgba_colormap()
        if not colormap:
            colormap = screen.get_rgb_colormap()
        self.set_colormap(colormap)

        win.show_all()
        self.shown = True

    # Init cairo surfaces
    def init_graphics(self):
        self.bgsurf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        self.strokesurf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        self.cr_bg = cairo.Context(self.bgsurf)
        self.cr_stroke = cairo.Context(self.strokesurf)
        self.cr_bg.set_source_rgba(0,0,0,0)
        self.cr_bg.paint()
        self.cr_stroke.set_source_rgb(1,1,1)
        self.cr_stroke.set_line_width(3)

        self.choice_bg_draw([self.USAGE],"Serif")

    # Init recognition engine
    def init_recog(self):
        self.candidates = None
        r_name, model_name, meta = Recognizer.get_all_available_models()[1]

        klass = Recognizer.get_available_recognizers()[r_name]
        self._recognizer = klass()
        self._recognizer.set_model(meta["name"])
        self._writing = Writing()


    #
    # Callbacks
    #

    def mouse_press(self,widget, event):
        if not self.faking:
            widget.set_decorated(not widget.get_decorated())
            return

        xie = XInputEvent([
            event.time,
            1,
            event.x,
            event.y,
            event.button],
            [self.width,self.height])
        self.process_input_event(xie)

    def mouse_release(self,widget, event):
        xie = XInputEvent([
            event.time,
            2,
            event.x,
            event.y,
            event.button],
            [self.width,self.height])
        self.process_input_event(xie)

    def mouse_motion(self,widget, event):
        xie = XInputEvent([
            event.time,
            0,
            event.x,
            event.y,
            0],
            [self.width,self.height])
        self.process_input_event(xie)

    def destroy(self):
        self.osdstate = self.ST_TERM
        self.xihandler.termme()
        gtk.Window.destroy(self)

    def expose(self,widget,event):
        cr = widget.window.cairo_create()

        # clear
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0,0,0,0.8)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        self.choice_draw(cr,event)
        self.strokes_draw(cr,event)
        self.cursor_draw(cr,event)

    # Called by the XInput handler
    # (or by the mouse_ methods)
    def process_input_event(self,event):
        if self.osdstate==self.ST_TERM:
            return

        self.tresolution = event.resolution

        # Do coord calculations
        if event.x!=0:
            # Use the square in the middle of the tablet
            border = (event.resolution[0]-event.resolution[1])/2
            event.x-= border
            if event.x<0: return
            if event.x>event.resolution[1]: return

            event.wx , event.wy = self.coordtrans_tablet_writing(event.x,event.y)
            event.x, event.y = self.coordtrans_tablet_osd(event.x,event.y)
            self.cpos = [event.x,event.y]


        if event.type==XInputEvent.XIE_PROX_IN:
            if not self.osdstate==self.ST_PROXOUT:
                print "PROXIN but state not PROXOUT,BUG?"
            self.osdstate = self.ST_PROXIN
            self.show_all()
            self.shown = True
            self.lastprox = None
            self.cursor_redraw = True
            self.get_window().invalidate_rect(gdk.Rectangle(0,0,0,0),False)

        elif event.type==XInputEvent.XIE_PROX_OUT:
            self.osdstate = self.ST_PROXOUT
            self.cpos = None
            self.cursor_invalidate()
            if not self.shown:
                print "PROX OUT but not shown,BUG?"
            self.lastprox = event.time
            gobject.timeout_add_seconds(5,self.hide,self.lastprox)

        elif event.type==XInputEvent.XIE_MOVE:
            self.cursor_invalidate()
            if self.osdstate==self.ST_DRAWING:
                self.strokes_move(event)
            elif self.osdstate==self.ST_CHOOSING:
                ch = self.choice_for_xy(event.x,event.y)
                if self.choice!=ch:
                    self.choice = ch
                    # invalidate the whole window if the selection changed
                    # theoretically old+new choice would be enough though
                    self.queue_draw()

        elif event.type==XInputEvent.XIE_BUTTON_PRESS:
            if event.button==1:
                self.osdstate = self.ST_DRAWING
                self.clear_bg()
                self.queue_draw()
                point = Point(event.wx,event.wy)
                if self._writing.get_n_strokes() == 0:
                    self.stroke1time = event.time
                    point.timestamp = 0
                else:
                    point.timestamp = event.time = self.stroke1time
                self.lastp = event
                self._writing.move_to_point(point)
            elif event.button==2:
                if self.candidates:
                    self.choice = self.choice_for_xy(event.x,event.y)
                    self.osdstate = self.ST_CHOOSING
                    self.queue_draw()
            elif event.button==3:
                if self._writing.get_n_strokes()>0:
                    self.clear()
                else:
                    self.osdstate = self.ST_CHOOSING
                    self.choice_cfg()
                    self.choice = self.choice_for_xy(event.x,event.y)

        elif event.type==XInputEvent.XIE_BUTTON_RELEASE:
            if event.button==1:
                if not self.osdstate==self.ST_DRAWING:
                    print "button 1 released but not drawing,BUG?"
                else:
                    if self._writing.get_n_strokes() == 0:
                        print "EEK"
                    if not self.strokes_async_running:
                        AsyncRunner(self.strokes_add_async,self.strokes_add_sync,self._writing.copy()).start()
                        self.strokes_async_running = True
                self.osdstate=self.ST_PROXIN
            elif event.button==2:
                if self.osdstate==self.ST_CHOOSING:
                    self.on_commit(self.candidates[self.choice])
            elif event.button==3:
                if self.osdstate==self.ST_CHOOSING and self.candidates==None:
                    ch = self.choice_for_xy(event.x,event.y)
                    self.choice_setmodel(ch)
                    self.clear()

    def choice_draw(self,cr,event):
        if self.osdstate == self.ST_CHOOSING:
            # highlight active choice
            cr.set_source_rgb(0,0,0.3)
            x = self.choice%self.choice_per_line
            y = self.choice/self.choice_per_line
            xfac,yfac = (
                    self.width/self.choice_per_line,
                    self.height/self.choice_per_line)
            cr.set_source_rgb(0,0,0.3)
            cr.rectangle(x*xfac,y*yfac,xfac,yfac)
            cr.fill()

        # draw candidates
        cr.set_source_surface(self.bgsurf)
        cr.paint()

    def strokes_draw(self,cr,event):
        if (self.osdstate==self.ST_CHOOSING):
            return

        if self._writing.get_n_strokes()>0:
            # darken the background
            cr.set_source_rgba(0,0,0,0.2)
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.paint()

        cr.set_source_surface(self.strokesurf)
        cr.paint()

    def cursor_draw(self,cr,event):
        if (self.osdstate==self.ST_PROXOUT) or self.faking:
            return

        if (self.cursor_redraw):
            cr.reset_clip()
            self.cursor_redraw = False

        cr.set_source_rgb(1,0,0)
        if self.cpos:
            x,y = tuple(self.cpos)
            cr.arc(x,y,self.CURSOR_RADIUS,0,2*math.pi)
            self.csext = map(lambda x: int(x),cr.stroke_extents())
            cr.stroke()

    def cursor_invalidate(self):
        if self.faking: return

        if self.csext:
            self.get_window().invalidate_rect(gdk.Rectangle( *self.csext),False)
        if self.cpos:
            self.get_window().invalidate_rect(gdk.Rectangle(
                self.cpos[0]-self.CURSOR_RADIUS,
                self.cpos[1]-self.CURSOR_RADIUS,
                self.CURSOR_RADIUS*2,
                self.CURSOR_RADIUS*2),False)

    # Draw current candidates on bg surface
    def choice_bg_draw(self,cand,fontname):
        cr = self.cr_bg
        cr.set_source_rgba(0,0,0,0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.rectangle(0,0,self.width,self.height)
        cr.fill()

        candc = len(cand)
        bperline = int(math.sqrt(candc+1))
        self.choice_per_line = bperline
        blen = self.width/bperline
        pctx = pangocairo.CairoContext(cr)
        layout = pctx.create_layout()
        layout.set_alignment(pango.ALIGN_CENTER)

        for j in range(self.choice_per_line):
            for i in range(self.choice_per_line):
                if len(cand)<=(j*bperline+i):
                    break
                cha = cand[j*bperline+i]
                layout.set_text(cha)
                fsize = 112
                bfactor = self.CHAR_FAC
                if len(cha)>10:
                    # text
                    bfactor = 1
                while True:
                    layout.set_font_description(
                        pango.FontDescription(
                            '%s %d' % (fontname,fsize)))
                    # ink extents
                    ex,ey,ew,eh = layout.get_pixel_extents()[0]
                    if (ew<=(blen*bfactor)) and (eh<=(blen*bfactor)): break
                    if fsize>30:
                        fsize = fsize*3/4
                    else:
                        fsize = fsize-2

                x = i*blen+blen/2 - ew/2 - ex
                y = j*blen+blen/2 - eh/2 - ey
                pctx.move_to(x,y)
                pctx.set_source_rgb(1,0,0)
                pctx.show_layout(layout)
        self.queue_draw()

    def choice_for_xy(self,x,y):
        PL = self.choice_per_line
        return PL*(y/(self.height/PL))+x/(self.width/PL)

    # Show model selection
    def choice_cfg(self):
        n = []
        for r_name, model_name, meta in Recognizer.get_all_available_models():
            n += ["%s\n%s" % (r_name,model_name)]
        if self.faking:
            n += ["Toggle Window Decorations"]
        self.choice_bg_draw(n,self.DEFAULT_FONT_CFG)

    # set the recognition model
    def choice_setmodel(self,nr):
        mcount = len(Recognizer.get_all_available_models())
        if (nr==mcount) and self.faking:
            self.set_decorated(not self.get_decorated())
            return
        elif nr>mcount:
            return
        r_name, model_name, meta = Recognizer.get_all_available_models()[nr]
        klass = Recognizer.get_available_recognizers()[r_name]
        self._recognizer = klass()
        self._recognizer.set_model(meta["name"])
        self._writing = Writing()

    # Called from gtk event thread when the async method is done
    def strokes_add_sync(self,res):
        writing,candidates = res
        if self._writing.get_n_strokes() != writing.get_n_strokes():
            # and again
            AsyncRunner(
                    self.strokes_add_async,
                    self.strokes_add_sync,
                    self._writing.copy()).start()
            # don't bother with our results
            return
        
        self.candidates = candidates
        self.choice_bg_draw(candidates,self.DEFAULT_FONT_CHAR)
        self.strokes_async_running = False

    def strokes_add_async(self,wr):
        self.normalize(wr)
        #wr.normalize_size()
        #wr.downsample_threshold(50)
        wr.smooth()
        wr.normalize_position()

        candidates = self._recognizer.recognize(wr, n=9)
        candidates = [char for char, prob in candidates]
        return (wr,candidates)

    def strokes_move(self,event):
        self.cr_stroke.set_source_rgb(1,1,1)
        self.cr_stroke.move_to(self.lastp.x,self.lastp.y)
        self.cr_stroke.line_to(event.x,event.y)
        ext = self.cr_stroke.stroke_extents()
        ext = map(lambda x: int(x),ext)
        self.cr_stroke.stroke()
        self.get_window().invalidate_rect(gdk.Rectangle(
                ext[0],ext[1],
                ext[2]-ext[0],
                ext[3]-ext[1]),False)
        if (self.lastp.wx!=event.wx) or (self.lastp.wy!=event.wy):
            self._writing.line_to_point(Point(event.wx,event.wy))
        self.lastp = event

    def on_commit(self,char):
        self.emit("commit-string", char)
        print "committed %s" % char
        fields = [char]
        if self.have_kanjidic:
            infos, readings, meanings = self.kanjidic_entry(char)
            fields += [
                    "\n".join(meanings),
                    "\n".join(readings),
                    "\n".join(infos)]
        self.clear_bg()
        self.choice_bg_draw(fields,"KanjiStrokeOrders,Serif")
        #self.strokesurf.write_to_png("/tmp/cairotest.png")
        self.clear(False)

    def hide(self,schedtime):
        if self.lastprox and self.lastprox == schedtime:
            self.hide_all()
            self.shown = False

    def clear_bg(self):
        cr = self.cr_bg
        cr.set_source_rgba(0,0,0,0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.rectangle(0,0,self.width,self.height)
        cr.paint()

    def clear(self,clear_bg=True):
        self._writing = Writing()
        self.candidates = None
        if clear_bg:
            self.clear_bg()
        cr = self.cr_stroke
        cr.set_source_rgba(0,0,0,0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        self.queue_draw()
        self.osdstate = self.ST_PROXIN

    def coordtrans_tablet_writing(self,x,y):
        sx = float(self._writing.get_width()) / self.tresolution[1]
        sy = float(self._writing.get_height()) / self.tresolution[1]
        x,y = (int(x * sx), int(y * sy))
        return x,y

    def coordtrans_tablet_osd(self,x,y):
        sx = float(self.width) / self.tresolution[1]
        sy = float(self.height) / self.tresolution[1]
        x,y = (int(x * sx), int(y * sy))
        return x,y

    # In contrast to tegaki's normalize this one keeps the aspect ratio intact.
    # Increases my chances with 日 (versus it's broader brother) for example.
    def normalize(self,wr):
        x, y, width, height = wr.size()
        prop = 0.9
        if float(width) / wr._width > Writing.NORMALIZE_MIN_SIZE:
            xrate = wr._width * prop / width
        else:
            xrate = 1.0
        if float(height) / wr._height > Writing.NORMALIZE_MIN_SIZE:
            yrate = wr._height * prop / height
        else:
            yrate = 1.0
        per = min(xrate,yrate)
        wr.resize(per,per)

    def kanjidic_entry(self,kanji):
        cmd = self.KANJIDIC_CMD % (kanji,self.DEFAULT_KANJIDIC_PATH)
        output = Popen(cmd, stdout=PIPE,shell=True).communicate()[0].strip()
        #print "kanjidic output: %s" % output
        info = []
        readings = []
        meanings = []

        for line in output.split("\n"):
            if re.search(".*:",line):
                info += [line]
            elif re.search("[a-zA-Z]",line):
                meanings += [line]
            else:
                readings += [line]

        return (info,meanings,readings)

gobject.signal_new("commit-string",
        TegakiOSD,
        gobject.SIGNAL_RUN_LAST,
        gobject.TYPE_NONE,
        (gobject.TYPE_PYOBJECT,))

if __name__ == "__main__":
    # Options
    from optparse import OptionParser

    parser = OptionParser(version="%prog " + VERSION)

    (options, args) = parser.parse_args()

    # Need threads for xinput
    gobject.threads_init()

    TegakiOSD()

    gtk.main()
