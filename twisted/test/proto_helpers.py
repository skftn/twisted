
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

from twisted.protocols import basic

class LineSendingProtocol(basic.LineReceiver):
    lostConn = False

    def __init__(self, lines, start = True):
        self.lines = lines[:]
        self.response = []
        self.start = start
    
    def connectionMade(self):
        if self.start:
            map(self.sendLine, self.lines)
    
    def lineReceived(self, line):
        if not self.start:
            map(self.sendLine, self.lines)
            self.lines = []
        self.response.append(line)
    
    def connectionLost(self, reason):
        self.lostConn = True
