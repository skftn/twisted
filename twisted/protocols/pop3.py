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

"""Post-office Protocol version 3
"""


from twisted.protocols import basic
import os, time, string, operator, stat, md5, binascii
from twisted.internet import protocol

class POP3Error(Exception):
    pass

class POP3(basic.LineReceiver):

    magic = None

    def connectionMade(self):
        if self.magic is None:
            self.magic = '<%s>' % time.time()
        self.mbox = None
        self.successResponse(self.magic)

    def successResponse(self, message=''):
        self.sendLine('+OK ' + str(message))

    def failResponse(self, message=''):
        self.sendLine('-ERR ' + str(message))

    def lineReceived(self, line):
        try:
            return apply(self.processCommand, tuple(string.split(line)))
        except (ValueError, AttributeError, POP3Error, TypeError), e:
            self.failResponse('bad protocol or server: %s: %s' % (e.__class__.__name__, e))
    
    def processCommand(self, command, *args):
        command = string.upper(command)
        if self.mbox is None and command != 'APOP':
            raise POP3Error("not authenticated yet: cannot do %s" % command)
        f = getattr(self, 'do_' + command, None)
        if f:
            return apply(getattr(self, 'do_'+command), args)
        raise POP3Error("Unknown protocol command: " + command)

    def do_APOP(self, user, digest):
        self.mbox = self.authenticateUserAPOP(user, digest)
        self.successResponse()

    def do_STAT(self):
        print self.mbox.listMessages()
        self.successResponse('%d 0' % reduce(operator.add, self.mbox.listMessages(), 0))

    def do_LIST(self, i=None):
        messages = self.mbox.listMessages()
        total = reduce(operator.add, messages, 0)
        self.successResponse(len(messages))
        i = 1
        for message in messages:
            if message:
                self.sendLine('%d %d' % (i, message))
            i = i+1
        self.sendLine('.')

    def do_UIDL(self, i=None):
        messages = self.mbox.listMessages()
        self.successResponse()
        for i in range(len(messages)):
            if messages[i]:
                self.sendLine('%d %s' % (i+1, self.mbox.getUidl(i)))
        self.sendLine('.')

    def getMessageFile(self, i):
        i = int(i)-1
        list = self.mbox.listMessages()
        try:
            resp = list[i]
        except IndexError:
            self.failResponse('index out of range')
            return None, None
        if not resp:
            self.failResponse('message deleted')
            return None, None
        return resp, self.mbox.getMessage(i)

    def do_TOP(self, i, size):
        resp, fp = self.getMessageFile(i)
        if not fp:
            return
        size = max(int(size), resp)
        self.successResponse(size)
        while size:
            line = fp.readline()
            if not line:
                break
            if line[-1] == '\n':
                line = line[:-1]
            if line[:1] == '.':
                line = '.'+line
            self.sendLine(line[:size])
            size = size-len(line[:size])
        self.sendLine('.')

    def do_RETR(self, i):
        resp, fp = self.getMessageFile(i)
        if not fp:
            return
        self.successResponse(resp)
        while 1:
            line = fp.readline()
            if not line:
                break
            if line[-1] == '\n':
                line = line[:-1]
            if line[:1] == '.':
                line = '.'+line
            self.sendLine(line)
        self.sendLine('.')

    def do_DELE(self, i):
        i = int(i)-1
        self.mbox.deleteMessage(i)
        self.successResponse()

    def do_QUIT(self):
        self.mbox.sync()
        self.successResponse()
        self.transport.loseConnection()

    def authenticateUserAPOP(self, user, digest):
        return Mailbox()


class Mailbox:

    def listMessages(self):
        return []
    def getMessage(self, i):
        raise ValueError
    def getUidl(self, i):
        raise ValueError
    def deleteMessage(self, i):
        raise ValueError
    def sync(self):
        pass


NONE, SHORT, FIRST_LONG, LONG = range(4)

NEXT = {}
NEXT[NONE] = NONE
NEXT[SHORT] = NONE
NEXT[FIRST_LONG] = LONG
NEXT[LONG] = NONE

class POP3Client(basic.LineReceiver):

    mode = SHORT
    command = 'WELCOME'
    import re
    welcomeRe = re.compile('<(.*)>')

    def sendShort(self, command, params):
        self.sendLine('%s %s' % (command, params))
        self.command = command
        self.mode = SHORT

    def sendLong(self, command, params):
        self.sendLine('%s %s' % (command, params))
        self.command = command
        self.mode = FIRST_LONG

    def handle_default(self, line):
        if line[:-4] == '-ERR':
            self.mode = NONE

    def handle_WELCOME(self, line):
        code, data = line.split(' ', 1)
        if code != '+OK':
            self.transport.loseConnection()
        else:
            m = self.welcomeRe.match(line)
            if m:
                self.welcomeCode = m.group(1)

    def _dispatch(self, command, default, *args):
        # print 'pop3client dispatching:', command, default, args
        try:
            method = getattr(self, 'handle_'+command, default)
            if method is not None:
                method(*args)
        except:
            from twisted.python import log
            log.deferr()

    def lineReceived(self, line):
        if self.mode == SHORT or self.mode == FIRST_LONG:
            self.mode = NEXT[self.mode]
            self._dispatch(self.command, self.handle_default, line)
        elif self.mode == LONG:
            if line == '.':
                self.mode = NEXT[self.mode]
                self._dispatch(self.command+'_end', None)
                return
            if line[:1] == '.':
                line = line[1:]
            self._dispatch(self.command+"_continue", None, line)

    def apopAuthenticate(self, user, password):
        digest = md5.new(magic+password).digest()
        digest = string.join(map(lambda x: "%02x"%ord(x), digest), '')
        self.apop(user, digest)

    def apop(self, user, digest):
        self.sendLong('APOP', user+' '+digest)
    def retr(self, i):
        self.sendLong('RETR', i)
    def dele(self, i):
        self.sendShort('DELE', i)
    def list(self, i=''):
        self.sendLong('LIST', i)
    def uidl(self, i=''):
        self.sendLong('UIDL', i)
    def user(self, name):
        self.sendShort('USER', name)
    def pass_(self, pass_):
        self.sendShort('PASS', pass_)
    def quit(self):
        self.sendShort('QUIT', '')
