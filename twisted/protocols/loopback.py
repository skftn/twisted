
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

# These class's names should have been based on Onanism, but were
# censored by the PSU

import protocol # See?  Their security protocol at work!!

class LoopbackRelay(protocol.Transport):

    buffer = ''
    shouldLose = 0

    def __init__(self, target, logFile=None):
        self.target = target
        self.logFile = logFile

    def write(self, data):
        #print "writing", `data`
        self.buffer = self.buffer + data
        if self.logFile:
            self.logFile.write("loopback writing %s\n" % repr(data))

    def clearBuffer(self):
        if self.logFile:
            self.logFile.write("loopback receiving %s\n" % repr(self.buffer))
        try:
            self.target.dataReceived(self.buffer)
        finally:
            self.buffer = ''
        if self.shouldLose:
            self.target.connectionLost()

    def loseConnection(self):
        self.shouldLose = 1

    def getHost(self):
        return 'loopback'

def loopback(server, client, logFile=None):
    serverToClient = LoopbackRelay(client, logFile)
    clientToServer = LoopbackRelay(server, logFile)
    server.makeConnection(serverToClient)
    client.makeConnection(clientToServer)
    while 1:
        serverToClient.clearBuffer()
        clientToServer.clearBuffer()
        if serverToClient.shouldLose:
            serverToClient.clearBuffer()
            break
        elif clientToServer.shouldLose:
            break
    client.connectionLost()
    server.connectionLost()
