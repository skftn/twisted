
# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gtk, string, sys, traceback, types

from twisted.python import explorer
from twisted.spread.ui import gtkutil
from twisted.internet import ingtkernet
from twisted.spread import pb
ingtkernet.install()

normalFont = gtk.load_font("-adobe-courier-medium-r-normal-*-*-120-*-*-m-*-iso8859-1")
font = normalFont
boldFont = gtk.load_font("-adobe-courier-bold-r-normal-*-*-120-*-*-m-*-iso8859-1")
errorFont = gtk.load_font("-adobe-courier-medium-o-normal-*-*-120-*-*-m-*-iso8859-1")

def findBeginningOfLineWithPoint(entry):
    pos = entry.get_point()
    while pos:
        pos = pos - 1
        #print 'looking at',pos
        c = entry.get_chars(pos, pos+1)
        #print 'found',repr(c)
        if c == '\n':
            #print 'got it!'
            return pos+1
    #print 'oops.'
    return 0

def isCursorOnFirstLine(entry):
    firstnewline = string.find(entry.get_chars(0,-1), '\n')
    if entry.get_point() <= firstnewline or firstnewline == -1:
        #print "cursor is on first line"
        return 1

def isCursorOnLastLine(entry):
    if entry.get_point() >= string.rfind(string.rstrip(entry.get_chars(0,-1)), '\n'):
        #print "cursor is on last line"
        return 1


class Interaction(gtk.GtkWindow):
    def __init__(self):
        gtk.GtkWindow.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_title("Manhole Interaction")

        vb = gtk.GtkVBox()
        vp = gtk.GtkVPaned()

        self.output = gtk.GtkText()
        gtkutil.defocusify(self.output)
        self.output.set_word_wrap(gtk.TRUE)
        vp.pack1(gtkutil.scrollify(self.output), gtk.TRUE, gtk.FALSE)

        self.input = gtk.GtkText()
        self.input.set_editable(gtk.TRUE)
        self.input.connect("key_press_event", self.processKey)
        self.input.set_word_wrap(gtk.TRUE)
        vp.pack2(gtkutil.scrollify(self.input), gtk.FALSE, gtk.TRUE)
        vb.pack_start(vp, 1,1,0)

        self.add(vb)
        self.input.grab_focus()
        self.signal_connect('destroy', gtk.mainquit, None)
        self.history = []
        self.histpos = 0

    loginWindow = None
    linemode = 0

    def historyUp(self):
        if self.histpos > 0:
            self.histpos = self.histpos - 1
            self.input.delete_text(0, -1)
            self.input.insert_defaults(self.history[self.histpos])
            self.input.set_point(1)

    def historyDown(self):
        if self.histpos < len(self.history) - 1:
            self.histpos = self.histpos + 1
            self.input.delete_text(0, -1)
            self.input.insert_defaults(self.history[self.histpos])
        elif self.histpos == len(self.history) - 1:
            self.histpos = self.histpos + 1
            self.input.delete_text(0, -1)

    def processKey(self, entry, event):
        if event.keyval == gtk.GDK.Return:
            l = self.input.get_length()
            # if l is 0, this coredumps gtk ;-)
            if not l:
                self.input.emit_stop_by_name("key_press_event")
                return
            lpos = findBeginningOfLineWithPoint(self.input)
            pt = entry.get_point()
            #print 'HELLO',pt,lpos
            isShift = event.state & gtk.GDK.SHIFT_MASK
            #print isShift
            if (self.input.get_chars(l-1,-1) == ":"):
                #print "woo!"
                self.linemode = 1
            elif isShift:
                self.linemode = 1
                self.input.insert_defaults('\n')
            elif (not self.linemode) or (pt == lpos):
                self.sendMessage(entry)
                self.input.delete_text(0, -1)
                self.input.emit_stop_by_name("key_press_event")
                self.linemode = 0
        elif event.keyval == gtk.GDK.Up and isCursorOnFirstLine(self.input):
            self.historyUp()
            gtk.idle_add(self.focusInput)
            self.input.emit_stop_by_name("key_press_event")
        elif event.keyval == gtk.GDK.Down and isCursorOnLastLine(self.input):
            self.historyDown()
            gtk.idle_add(self.focusInput)
            self.input.emit_stop_by_name("key_press_event")

    def focusInput(self):
        self.input.grab_focus()
        return gtk.FALSE # do not requeue
    maxBufSz = 10000

    def messageReceived(self, message):
        # print "received: ", message
        t = self.output
        t.set_point(t.get_length())
        t.freeze()
        for element in message:
            # print 'processing',element
            t.insert(font, self.textStyles[element[0]], None, element[1])
        l = t.get_length()
        diff = self.maxBufSz - l
        if diff < 0:
            diff = - diff
            t.delete_text(0,diff)
        t.thaw()
        a = t.get_vadjustment()
        a.set_value(a.upper - a.page_size)
        self.input.grab_focus()

    def browseObjectReceived(self, obj):
        """Display a browser ObjectLink.
        """
        # This is a stop-gap implementation.  Ideally, everything
        # would be nicely formatted with pretty colours and you could
        # select referenced objects to browse them with
        # browse(selectedLink.identifier)

        if obj.type in map(explorer.typeString, [type.FunctionType,
                                                 type.MethodType]):
            arglist = []
            for arg in obj.value['signature']:
                if arg.has_key('default'):
                    a = "%s=%s" % (arg['name'], arg['default'])
                elif arg.has_key('list'):
                    a = "*%s" % (arg['name'],)
                elif arg.has_key('keywords'):
                    a = "**%s" % (arg['name'],)
                else:
                    a = arg['name']
                arglist.append(a)

            things = ''
            if obj.value.has_key('class'):
                things = "Class: %s\n" % (obj.value['class'],)
            if obj.value.has_key('self'):
                things = things + "Self: %s\n" % (obj.value['self'],)

            s = "%(name)s(%(arglist)s)\n%(things)s\n%(doc)s\n" % {
                'name': obj.value['name'],
                'doc': obj.value['doc'],
                'things': things,
                'arglist': string.join(arglist,", "),
                }
        else:
            s = str(obj) + '\n'

        self.messageReceived([('out',s)])

    blockcount = 0

    def sendMessage(self, unused_data=None):
        text = self.input.get_chars(0,-1)
        if self.linemode:
            self.blockcount = self.blockcount + 1
            fmt = ">>> # begin %s\n%%s\n#end %s\n" % (
                self.blockcount, self.blockcount)
        else:
            fmt = ">>> %s\n"
        self.history.append(text)
        self.histpos = len(self.history)
        self.messageReceived([['command',fmt % text]])

        method = self.perspective.do
        callback = self.messageReceived

        split = string.split(text,' ',1)
        if len(split) == 2:
            (statement, remainder) = split
            if statement == 'browse':
                method = self.perspective.browse
                text = remainder
                callback = self.browseObjectReceived

        try:
            method(text, pbcallback=callback)
        except pb.ProtocolError:
            # ASSUMPTION: pb.ProtocolError means we lost our connection.
            (eType, eVal, tb) = sys.exc_info()
            del tb
            s = string.join(traceback.format_exception_only(eType, eVal),
                            '')
            self.connectionLost(s)
        except:
            traceback.print_exc()
            gtk.mainquit()


    def connected(self, perspective):
        self.loginWindow.hide()
        self.name = self.loginWindow.username.get_text()
        self.hostname = self.loginWindow.hostname.get_text()
        perspective.broker.notifyOnDisconnect(self.connectionLost)
        self.perspective = perspective
        self.show_all()
        self.set_title("Manhole: %s@%s" % (self.name, self.hostname))
        win = self.get_window()
        blue = win.colormap.alloc(0x0000, 0x0000, 0xffff)
        red = win.colormap.alloc(0xffff, 0x0000, 0x0000)
        orange = win.colormap.alloc(0xaaaa, 0x8888, 0x0000)
        black = win.colormap.alloc(0x0000, 0x0000, 0x0000)
        gray = win.colormap.alloc(0x6666, 0x6666, 0x6666)
        self.textStyles = {"out": black,   "err": orange,
                           "result": blue, "error": red,
                           "command": gray}

    def connectionLost(self, reason=None):
        if not reason:
            reason = "Connection Lost"
        self.loginWindow.loginReport(reason)
        self.hide()
        self.loginWindow.show()

class ObjectLink(pb.RemoteCopy, explorer.ObjectLink):
    """RemoteCopy of explorer.ObjectLink"""

    def __init__(self):
        pass

    __str__ = explorer.ObjectLink.__str__

pb.setCopierForClass('twisted.python.explorer.ObjectLink',
                     ObjectLink)
