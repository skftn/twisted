
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

"""Test cases for 'jelly' object serialization.
"""

import types
from twisted.trial import unittest
from twisted.spread import jelly, pb
#from twisted import sexpy

from twisted.python.compat import bool

class A:
    """
    dummy class
    """
    def amethod(self):
        pass

def afunc(self):
    pass

class B:
    """
    dummy class
    """
    def bmethod(self):
        pass


class C:
    """
    dummy class
    """
    def cmethod(self):
        pass


class SimpleJellyTest:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        
    def isTheSameAs(self, other):
        return self.__dict__ == other.__dict__

try:
    object
    haveObject = 0 # 1 # more work to be done before this really works
except:
    haveObject = 0
else:
    class NewStyle(object):
        pass


class JellyTestCase(unittest.TestCase):
    """
    testcases for `jelly' module serialization.
    """

    def testMethodSelfIdentity(self):
        a = A()
        b = B()
        a.bmethod = b.bmethod
        b.a = a
        im_ = jelly.unjelly(jelly.jelly(b)).a.bmethod
        self.assertEquals(im_.im_class, im_.im_self.__class__)

    if haveObject:
        def testNewStyle(self):
            n = NewStyle()
            n.x = 1
            n2 = NewStyle()
            n.n2 = n2
            n.n3 = n2
            c = jelly.jelly(n)
            m = jelly.unjelly(c)
            self.failUnless(isinstance(m, NewStyle))
            self.assertIdentical(m.n2, m.n3)

    def testSimple(self):
        """
        simplest test case
        """
        self.failUnless(SimpleJellyTest('a', 'b').isTheSameAs(SimpleJellyTest('a', 'b')))
        a = SimpleJellyTest(1, 2)
        cereal = jelly.jelly(a)
        b = jelly.unjelly(cereal)
        self.failUnless(a.isTheSameAs(b))

    def testIdentity(self):
        """
        test to make sure that objects retain identity properly
        """
        x = []
        y = (x)
        x.append(y)
        x.append(y)
        self.assertIdentical(x[0], x[1])
        self.assertIdentical(x[0][0], x)
        s = jelly.jelly(x)
        z = jelly.unjelly(s)
        self.assertIdentical(z[0], z[1])
        self.assertIdentical(z[0][0], z)

    def testUnicode(self):
        if hasattr(types, 'UnicodeType'):
            x = 'blah'
            self.assertEquals(jelly.unjelly(jelly.jelly(unicode(x))), x)

    def testStressReferences(self):
        reref = []
        toplevelTuple = ({'list': reref}, reref)
        reref.append(toplevelTuple)
        s = jelly.jelly(toplevelTuple)
        z = jelly.unjelly(s)
        self.assertIdentical(z[0]['list'], z[1])
        self.assertIdentical(z[0]['list'][0], z)


    def testPersistentStorage(self):
        perst = [{}, 1]
        def persistentStore(obj, jel, perst = perst):
            perst[1] = perst[1] + 1
            perst[0][perst[1]] = obj
            return str(perst[1])

        def persistentLoad(pidstr, unj, perst = perst):
            pid = int(pidstr)
            return perst[0][pid]

        a = SimpleJellyTest(1, 2)
        b = SimpleJellyTest(3, 4)
        c = SimpleJellyTest(5, 6)

        a.b = b
        a.c = c
        c.b = b

        jel = jelly.jelly(a, persistentStore = persistentStore)
        x = jelly.unjelly(jel, persistentLoad = persistentLoad)

        self.assertIdentical(x.b, x.c.b)
        # assert len(perst) == 3, "persistentStore should only be called 3 times."
        self.failUnless(perst[0], "persistentStore was not called.")
        self.assertIdentical(x.b, a.b, "Persistent storage identity failure.")

    def testMoreReferences(self):
        a = []
        t = (a,)
        a.append((t,))
        s = jelly.jelly(t)
        z = jelly.unjelly(s)
        self.assertIdentical(z[0][0][0], z)

    def testTypeSecurity(self):
        """
        test for type-level security of serialization
        """
        taster = jelly.SecurityOptions()
        dct = jelly.jelly({})
        try:
            jelly.unjelly(dct, taster)
            self.fail("Insecure Jelly unjellied successfully.")
        except jelly.InsecureJelly:
            # OK, works
            pass

    def testLotsaTypes(self):
        """
        test for all types currently supported in jelly
        """
        a = A()
        jelly.unjelly(jelly.jelly(a))
        jelly.unjelly(jelly.jelly(a.amethod))
        items = [afunc, [1, 2, 3], not bool(1), bool(1), 'test', 20.3, (1,2,3), None, A, unittest, {'a':1}, A.amethod]
        for i in items:
            self.assertEquals(i, jelly.unjelly(jelly.jelly(i)))
    
    def testSetState(self):
        global TupleState
        class TupleState:
            def __init__(self, other):
                self.other = other
            def __getstate__(self):
                return (self.other,)
            def __setstate__(self, state):
                self.other = state[0]
            def __hash__(self):
                return hash(self.other)
        a = A()
        t1 = TupleState(a)
        t2 = TupleState(a)
        t3 = TupleState((t1, t2))
        d = {t1: t1, t2: t2, t3: t3, "t3": t3}
        t3prime = jelly.unjelly(jelly.jelly(d))["t3"]
        self.assertIdentical(t3prime.other[0].other, t3prime.other[1].other)

    def testClassSecurity(self):
        """
        test for class-level security of serialization
        """
        taster = jelly.SecurityOptions()
        taster.allowInstancesOf(A, B)
        a = A()
        b = B()
        c = C()
        # add a little complexity to the data
        a.b = b
        a.c = c
        # and a backreference
        a.x = b
        b.c = c
        # first, a friendly insecure serialization
        friendly = jelly.jelly(a, taster)
        x = jelly.unjelly(friendly, taster)
        self.failUnless(isinstance(x.c, jelly.Unpersistable),
                        "C came back: %s" % x.c.__class__)
        # now, a malicious one
        mean = jelly.jelly(a)
        try:
            x = jelly.unjelly(mean, taster)
            self.fail("x came back: %s" % x)
        except jelly.InsecureJelly:
            # OK
            pass
        self.assertIdentical(x.x, x.b, "Identity mismatch")
        #test class serialization
        friendly = jelly.jelly(A, taster)
        x = jelly.unjelly(friendly, taster)
        self.assertIdentical(x, A, "A came back: %s" % x)

class ClassA(pb.Copyable, pb.RemoteCopy):
    def __init__(self):
        self.ref = ClassB(self)

class ClassB(pb.Copyable, pb.RemoteCopy):
    def __init__(self, ref):
        self.ref = ref

class CircularReferenceTestCase(unittest.TestCase):
    def testSimpleCircle(self):
        a = jelly.unjelly(jelly.jelly(ClassA()))
        self.failUnless(a.ref.ref is a, "Identity not preserved in circular reference")

testCases = [JellyTestCase, CircularReferenceTestCase]
