
import insults
from telnet import TelnetTransport, TelnetBootstrapProtocol
from ssh import session, TerminalUser, TerminalSession, TerminalSessionTransport, ConchFactory

from twisted.python import components
from twisted.internet import protocol
from twisted.application import internet, service

def makeService(args):
    class ConstructedProtocol(insults.ServerProtocol):
        handlerFactory = args['handler']

    # Telnet classes
    class ConstructedBootstrap(TelnetBootstrapProtocol):
        protocolFactory = ConstructedProtocol

    class ConstructedTelnetTransport(TelnetTransport):
        protocolFactory = ConstructedBootstrap

    # SSH classes
    class ConstructedSessionTransport(TerminalSessionTransport):
        protocolFactory = ConstructedProtocol

    class ConstructedSession(TerminalSession):
        transportFactory = ConstructedSessionTransport

    # XXX Can only support one handler via ssh per process!  Muy suck.
    components.registerAdapter(ConstructedSession, TerminalUser, session.ISession)

    f = protocol.ServerFactory()
    f.protocol = ConstructedTelnetTransport
    tsvc = internet.TCPServer(args['telnet'], f)

    f = ConchFactory()
    csvc = internet.TCPServer(args['ssh'], f)

    m = service.MultiService()
    tsvc.setServiceParent(m)
    csvc.setServiceParent(m)
    return m

