# Twisted, the Framework of Your Internet
# Copyright (C) 2001-2003 Matthew W. Lefkowitz
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
#
from twisted.trial import unittest
from twisted.application import app, service
from twisted.persisted import sob
import os

class TestAppSupport(unittest.TestCase):

    def testSaveApplication(self):
        a = service.Application("hello")
        for style in 'pickle xml source'.split():
            app.saveApplication(a, style, 0, 'helloapplication')
            a1 = app.loadPersisted('helloapplication', style, None)
            self.assertEqual(service.IService(a1).name, "hello")
            app.saveApplication(a, style, 0, None)
            a1 = app.loadPersisted('hello.ta'+style[0], style, None)
            self.assertEqual(service.IService(a1).name, "hello")
        open("hello.tac", 'w').write("""
from twisted.application import service
application = service.Application("hello")
""")
        a1 = app.loadPersisted('hello.tac', 'python', None)
        self.assertEqual(service.IService(a1).name, "hello")
        
    def testTypeGuesser(self):
        self.assertRaises(KeyError, app.guessType, "file.blah")
        self.assertEqual('python', app.guessType("file.py"))
        self.assertEqual('python', app.guessType("file.tac"))
        self.assertEqual('python', app.guessType("file.etac"))
        self.assertEqual('pickle', app.guessType("file.tap"))
        self.assertEqual('pickle', app.guessType("file.etap"))
        self.assertEqual('source', app.guessType("file.tas"))
        self.assertEqual('source', app.guessType("file.etas"))
        self.assertEqual('xml', app.guessType("file.tax"))
        self.assertEqual('xml', app.guessType("file.etax"))

    def testPassphrase(self):
        self.assertEqual(app.getPassphrase(0), None)

    def testLoadApplication(self):
        a = service.Application("hello")
        baseconfig = {'file': None, 'xml': None, 'source': None, 'python':None}
        for style in 'source xml pickle'.split():
            config = baseconfig.copy()
            config[{'pickle': 'file'}.get(style, style)] = 'helloapplication'
            app.saveApplication(a, style, 0, 'helloapplication')
            a1 = app.loadApplication(config, None)
            self.assertEqual(service.IService(a1).name, "hello")
        config = baseconfig.copy()
        config['python'] = 'helloapplication'
        open("helloapplication", 'w').write("""
from twisted.application import service
application = service.Application("hello")
""")
        a1 = app.loadApplication(config, None)
        self.assertEqual(service.IService(a1).name, "hello")

    def test_loadOrCreate(self):
        # make sure nothing exists
        file = "applicationfile"
        if os.path.exists(file):
            os.remove(file)
        appl = app.loadOrCreate("lala", file, "procname", 5, 7)
        self.assertEqual(service.IProcess(appl).uid, 5)
        self.assertEqual(service.IProcess(appl).gid, 7)
        self.assertEqual(service.IProcess(appl).processName, "procname")
        self.assertEqual(list(service.IServiceCollection(appl)), [])
        self.assertEqual(service.IService(appl).name, "lala")
        self.assertEqual(sob.IPersistable(appl).name, "lala")
        self.assertEqual(sob.IPersistable(appl).style, "pickle")
        sob.IPersistable(appl).save(filename=file)
        appl = app.loadOrCreate("lolo", file, "notname", 8, 9)
        self.assertEqual(service.IProcess(appl).uid, 5)
        self.assertEqual(service.IProcess(appl).gid, 7)
        self.assertEqual(service.IProcess(appl).processName, "notname")
        self.assertEqual(list(service.IServiceCollection(appl)), [])
        self.assertEqual(service.IService(appl).name, "lala")
        self.assertEqual(sob.IPersistable(appl).name, "lala")
        self.assertEqual(sob.IPersistable(appl).style, "pickle")

    def test_convertStyle(self):
        appl = service.Application("lala")
        for instyle in 'xml source pickle'.split():
            for outstyle in 'xml source pickle'.split():
                sob.IPersistable(appl).setStyle(instyle)
                sob.IPersistable(appl).save(filename="converttest")
                app.convertStyle("converttest", instyle, None,
                                 "converttest.out", outstyle, 0)
                appl2 = app.loadPersisted("converttest.out", outstyle, None)
                self.assertEqual(service.IService(appl2).name, "lala")
