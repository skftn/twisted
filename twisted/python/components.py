# -*- test-case-name: twisted.test.test_components -*-

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

"""Component architecture for Twisted, based on Zope3 components.

IMPORTANT: In old code the meaning of 'implementing' was too vague. In this
version we will switch to the Zope3 meaning (objects provide interfaces,
if a class implements interfaces that means its *instances* provide them).
However, some methods (e.g. implements()) are confusing because they actually
check if object *provides* an interface.

Using the Zope3 API directly is thus strongly recommended. Everything
you need is in the top-level of the zope.interface package, e.g.:

   from zope.interface import Interface

The one exception is registerAdapter, which is in this module and is
still the way to register adapters (at least, if you want Twisted's
global adapter registry).

Possible bugs in your code may happen because you rely on
__implements__ existing and/or have only that and assumes that means
the component system knows it implements interfaces. This compat layer
will do its best to make sure that is the case, but sometimes it will
fail on edge cases, and it will always fail if you use zope.interface APIs directly,
e.g. this code will NOT WORK AS EXPECTED:

    from twisted.python.components import implements
    class Foo:
        __implements__ = IFoo,
    IFoo.providedBy(Foo()) # returns False, not True
    implements(Foo(), IFoo) # True! notice meaning of 'implements' changed
    IFoo.providedBy(Foo()) # now returns True, since implements() fixed it

The lesson - just switch all your code to zope.interface, or only use
old APIs. These are slow and will whine a lot. Use zope.interface.
"""

# twisted imports
from twisted.python import reflect, util, context
from twisted.persisted import styles

# system imports
import sys
import types
import warnings
import weakref

# zope3
try:
    from zope.interface import interface, declarations
    from zope.interface.adapter import AdapterRegistry as ZopeAdapterRegistry
except ImportError:
    raise ImportError, "you need zope.interface installed (http://zope.org/Products/ZopeInterface/)"


ALLOW_DUPLICATES = 0

class _Nothing:
    """
    An alternative to None - default value for functions which raise if default not passed.
    """


def getRegistry(r):
    return _theAdapterRegistry

class CannotAdapt(NotImplementedError, TypeError):
    """
    Can't adapt some object to some Interface.
    """


_adapterPersistence = weakref.WeakValueDictionary()
_adapterOrigPersistence = weakref.WeakValueDictionary()

class MetaInterface(interface.InterfaceClass):

    def __init__(self, name, bases=(), attrs=None, __doc__=None,
                 __module__=None):
        if attrs is not None:
            if attrs.has_key("__adapt__"):
                warnings.warn("Please don't use __adapt__ on Interface subclasses", DeprecationWarning, stacklevel=2)
                self.__instadapt__ = attrs["__adapt__"]
                del attrs["__adapt__"]
            for k, v in attrs.items():
                if not isinstance(v, types.FunctionType) and not isinstance(v, interface.Attribute):
                    attrs[k] = interface.Attribute(repr(v))
        # BEHOLD A GREAT EVIL SHALL COME UPON THEE
        if __module__ == None:
            __module__ = sys._getframe(1).f_globals['__name__']
        return interface.InterfaceClass.__init__(self, name, bases, attrs, __doc__, __module__)

    def __call__():
        # Copying evil trick I dinna understand
        def __call__(self, adaptable, default=_Nothing, persist=None, registry=None):
            if hasattr(adaptable, "__class__"):
                fixClassImplements(adaptable.__class__)
            if registry != None:
                raise RuntimeError, "registry argument will be ignored"
            # getComponents backwards compat
            if hasattr(adaptable, "getComponent") and not hasattr(adaptable, "__conform__") and persist != False:
                warnings.warn("please use __conform__ instead of getComponent: %s" % type(adaptable), DeprecationWarning)
                result = adaptable.getComponent(self)
                if result != None:
                    return result
            # check for weakref persisted adapters
            if persist != False:
                pkey = (id(adaptable), self)
                if _adapterPersistence.has_key(pkey):
                    return _adapterPersistence[pkey]

            if persist:
                # we need to recreate the whole z.i.i.Interface.__call__
                # code path here, cause we should only persist stuff
                # that isn't coming from __conform__. Sigh.
                conform = getattr(adaptable, '__conform__', None)
                if conform is not None:
                    try:
                        adapter = conform(self)
                    except TypeError:
                        if sys.exc_info()[2].tb_next is not None:
                            raise CannotAdapt
                    else:
                        if adapter is not None:
                            return adapter
                adapter = self.__adapt__(adaptable)
                if adapter == None:
                    if default == _Nothing:
                        raise CannotAdapt
                    else:
                        return default
                _adapterPersistence[(id(adaptable), self)] = adapter
                # make sure as long as adapter is alive the original object is alive
                _adapterOrigPersistence[_Wrapper(adaptable)] = adapter
                return adapter
            
            marker = object()
            adapter = interface.InterfaceClass.__call__(self, adaptable, alternate=marker)
            if adapter == marker:
                if hasattr(self, '__instadapt__'):
                    adapter = self.__instadapt__(adaptable, default)
                else:
                    adapter = default
            if adapter == default and default == _Nothing:
                raise CannotAdapt
            return adapter
        
        return __call__
    __call__ = __call__()
    
    def adaptWith(self, using, to, registry=None):
        if registry != None:
            raise RuntimeError, "registry argument will be ignored"
        warnings.warn("adaptWith is only supported for backwards compatability", DeprecationWarning)
        registry = _theAdapterRegistry
        registry.register([self], to, '', using)

    def __getattr__(self, attr):
        warnings.warn("Don't get attributes off Interface, use .queryDescriptionFor() etc. instead", DeprecationWarning)
        result = self.queryDescriptionFor(attr)
        if result == None:
            raise AttributeError, attr
        return result


Interface = MetaInterface("Interface", __module__="twisted.python.components")

def tupleTreeToList(t, l=None):
    """Convert an instance, or tree of tuples, into list."""
    if l is None: l = []
    if isinstance(t, types.TupleType):
        for o in t:
            tupleTreeToList(o, l)
    else:
        l.append(t)
    return l


def implements(obj, interfaceClass):
    """DEPRECATED. Return boolean indicating if obj *provides* the given interface.

    This method checks if object provides, not if it implements. The confusion
    is due to the change in terminology.
    """
    warnings.warn("Please use providedBy() or implementedBy()", DeprecationWarning, stacklevel=2)
    # try to support both classes and instances, which is HORRIBLE
    if isinstance(obj, (type, types.ClassType)):
        fixClassImplements(obj)
        return interfaceClass.implementedBy(obj)
    else:
        fixClassImplements(obj.__class__)
        return interfaceClass.providedBy(obj)


def getInterfaces(klass):
    """DEPRECATED. Return list of all interfaces the class implements. Or the object provides.

    This is horrible and stupid. Please use zope.interface.providedBy() or implementedBy().
    """
    warnings.warn("getInterfaces should not be used, use providedBy() or implementedBy()", DeprecationWarning, stacklevel=2)
    # try to support both classes and instances, giving different behaviour
    # which is HORRIBLE :(
    if isinstance(klass, (type, types.ClassType)):
        fixClassImplements(klass)
        l = list(declarations.implementedBy(klass))
    else:
        fixClassImplements(klass.__class__)
        l = list(declarations.providedBy(klass))
    r = []
    for i in l:
        r.extend(superInterfaces(i))
    return util.uniquify(r)


def superInterfaces(interface):
    """DEPRECATED. Given an interface, return list of super-interfaces (including itself)."""
    warnings.warn("Please use zope.interface APIs", DeprecationWarning, stacklevel=2)
    result = [interface]
    result.extend(reflect.allYourBase(interface, Interface))
    result = util.uniquify(result)
    if Interface in result:
        result.remove(Interface)
    return result


class _Wrapper(object):
    """Makes any object be able to be dict key."""

    __slots__ = ["a"]

    def __init__(self, a):
        self.a = a


_fixedClasses = {}
def fixClassImplements(klass):
    """Switch class from __implements__ to zope implementation."""
    if _fixedClasses.has_key(klass):
        return
    if hasattr(klass, "__implements__") and isinstance(klass.__implements__, (tuple, MetaInterface)):
        warnings.warn("Please use implements(), not __implements__ for class %s" % klass, DeprecationWarning, stacklevel=3)
        declarations.classImplementsOnly(klass, *tupleTreeToList(klass.__implements__))
        _fixedClasses[klass] = 1

def registerAdapter(adapterFactory, origInterface, *interfaceClasses):
    """Register an adapter class.

    An adapter class is expected to implement the given interface, by
    adapting instances implementing 'origInterface'. An adapter class's
    __init__ method should accept one parameter, an instance implementing
    'origInterface'.
    """
    self = _theAdapterRegistry
    assert interfaceClasses, "You need to pass an Interface"
    global ALLOW_DUPLICATES

    # deal with class->interface adapters:
    if not issubclass(origInterface, Interface):
        # fix up __implements__ if it's old style
        fixClassImplements(origInterface)
        origInterface = declarations.implementedBy(origInterface)

    for interfaceClass in interfaceClasses:
        factory = self.get(origInterface).selfImplied.get(interfaceClass, {}).get('')
        if (factory and not ALLOW_DUPLICATES):
            raise ValueError("an adapter (%s) was already registered." % (factory, ))
    for interfaceClass in interfaceClasses:
        self.register([origInterface], interfaceClass, '', adapterFactory)


def getAdapterFactory(fromInterface, toInterface, default):
    """Return registered adapter for a given class and interface.
    """
    fixClassImplements(fromInterface)
    self = _theAdapterRegistry
    if not issubclass(fromInterface, Interface):
        fromInterface = declarations.implementedBy(fromInterface)
    factory = self.lookup1(fromInterface, toInterface)
    if factory == None:
        factory = default
    return factory

getAdapterClass = getAdapterFactory

def getAdapterClassWithInheritance(klass, interfaceClass, default):
    """Return registered adapter for a given class and interface.
    """
    fixClassImplements(klass)
    adapterClass = getAdapterFactory(klass, interfaceClass, _Nothing)
    if adapterClass is _Nothing:
        for baseClass in reflect.allYourBase(klass):
            adapterClass = getAdapterFactory(klass, interfaceClass, _Nothing)
            if adapterClass is not _Nothing:
                return adapterClass
    else:
        return adapterClass
    return default

def getAdapter(obj, interfaceClass, default=_Nothing,
               adapterClassLocator=None, persist=None):
    """Return an object that implements the given interface.

    The result will be a wrapper around the object passed as a parameter, or
    the parameter itself if it already implements the interface. If no
    adapter can be found, the 'default' parameter will be returned.
    """
    if hasattr(obj, '__class__'):
        fixClassImplements(obj.__class__)
    self = _theAdapterRegistry
    if interfaceClass.providedBy(obj):
        return obj

    if persist != False:
        pkey = (id(obj), interfaceClass)
        if _adapterPersistence.has_key(pkey):
            return _adapterPersistence[pkey]

    factory = self.lookup1(declarations.providedBy(obj), interfaceClass)
    if factory != None:
        return factory(obj)

    if default == _Nothing:
        raise NotImplementedError
    else:
        return default


_theAdapterRegistry = ZopeAdapterRegistry()
# add global adapter lookup hook for our newly created registry
def _hook(iface, ob, lookup=_theAdapterRegistry.lookup1):
    factory = lookup(declarations.providedBy(ob), iface)
    if factory is None:
        return None
    else:
        return factory(ob)
interface.adapter_hooks.append(_hook)

# public zopey registration hook
register = _theAdapterRegistry.register


class Adapter:
    """I am the default implementation of an Adapter for some interface.

    This docstring contains a limerick, by popular demand::

        Subclassing made Zope and TR
        much harder to work with by far.
            So before you inherit,
            be sure to declare it
        Adapter, not PyObject*

    @cvar temporaryAdapter: If this is True, the adapter will not be
          persisted on the Componentized.
    @cvar multiComponent: If this adapter is persistent, should it be
          automatically registered for all appropriate interfaces.
    """

    # These attributes are used with Componentized.

    temporaryAdapter = 0
    multiComponent = 1

    def __init__(self, original):
        """Set my 'original' attribute to be the object I am adapting.
        """
        self.original = original

    def getComponent(self, interface, registry=None, default=None):
        """
        I forward getComponent to self.original if it has it, otherwise I
        simply return default.
        """
        if hasattr(self.original, "__conform__"):
            result = self.original.__conform__(interface)
            if result == None:
                result = default
            return result
        try:
            f = self.original.getComponent
        except AttributeError:
            return default
        else:
            warnings.warn("please use __conform__ instead of getComponent on %r's class" % self.original, DeprecationWarning, stacklevel=2)
            return f(interface, registry=registry, default=default)

    def __conform__(self, interface):
        return self.getComponent(interface)
    
    def isuper(self, iface, adapter):
        """
        Forward isuper to self.original
        """
        return self.original.isuper(iface, adapter)


class Componentized(styles.Versioned):
    """I am a mixin to allow you to be adapted in various ways persistently.

    I define a list of persistent adapters.  This is to allow adapter classes
    to store system-specific state, and initialized on demand.  The
    getComponent method implements this.  You must also register adapters for
    this class for the interfaces that you wish to pass to getComponent.

    Many other classes and utilities listed here are present in Zope3; this one
    is specific to Twisted.
    """

    persistenceVersion = 1

    def __init__(self):
        self._adapterCache = {}

    def locateAdapterClass(self, klass, interfaceClass, default, registry=None):
        return getAdapterClassWithInheritance(klass, interfaceClass, default)

    def setAdapter(self, interfaceClass, adapterClass):
        self.setComponent(interfaceClass, adapterClass(self))

    def addAdapter(self, adapterClass, ignoreClass=0, registry=None):
        """Utility method that calls addComponent.  I take an adapter class and
        instantiate it with myself as the first argument.

        @return: The adapter instantiated.
        """
        adapt = adapterClass(self)
        self.addComponent(adapt, ignoreClass, registry)
        return adapt

    def setComponent(self, interfaceClass, component):
        """
        """
        if hasattr(component, "__class__"):
            fixClassImplements(component.__class__)
        self._adapterCache[reflect.qual(interfaceClass)] = component

    def addComponent(self, component, ignoreClass=0, registry=None):
        """
        Add a component to me, for all appropriate interfaces.

        In order to determine which interfaces are appropriate, the component's
        provided interfaces will be scanned.

        If the argument 'ignoreClass' is True, then all interfaces are
        considered appropriate.

        Otherwise, an 'appropriate' interface is one for which its class has
        been registered as an adapter for my class according to the rules of
        getComponent.

        @return: the list of appropriate interfaces
        """
        if hasattr(component, "__class__"):
            fixClassImplements(component.__class__)
        for iface in declarations.providedBy(component):
            if (ignoreClass or
                (self.locateAdapterClass(self.__class__, iface, None, registry)
                 == component.__class__)):
                self._adapterCache[reflect.qual(iface)] = component
        
    def unsetComponent(self, interfaceClass):
        """Remove my component specified by the given interface class."""
        del self._adapterCache[reflect.qual(interfaceClass)]

    def removeComponent(self, component):
        """
        Remove the given component from me entirely, for all interfaces for which
        it has been registered.

        @return: a list of the interfaces that were removed.
        """
        if (isinstance(component, types.ClassType) or
            isinstance(component, types.TypeType)):
            warnings.warn("passing interface to removeComponent, you probably want unsetComponent", DeprecationWarning, 1)
            self.unsetComponent(component)
            return [component]
        l = []
        for k, v in self._adapterCache.items():
            if v is component:
                del self._adapterCache[k]
                l.append(reflect.namedObject(k))
        return l
    
    def getComponent(self, interface, registry=None, default=None):
        """Create or retrieve an adapter for the given interface.

        If such an adapter has already been created, retrieve it from the cache
        that this instance keeps of all its adapters.  Adapters created through
        this mechanism may safely store system-specific state.

        If you want to register an adapter that will be created through
        getComponent, but you don't require (or don't want) your adapter to be
        cached and kept alive for the lifetime of this Componentized object,
        set the attribute 'temporaryAdapter' to True on your adapter class.

        If you want to automatically register an adapter for all appropriate
        interfaces (with addComponent), set the attribute 'multiComponent' to
        True on your adapter class.
        """
        registry = getRegistry(registry)
        k = reflect.qual(interface)
        if self._adapterCache.has_key(k):
            return self._adapterCache[k]
        else:
            adapter = interface.__adapt__(self)
            if hasattr(adapter, "__class__"):
                fixClassImplements(adapter.__class__)
            if adapter is not None and adapter is not _Nothing and not (
                hasattr(adapter, "temporaryAdapter") and
                adapter.temporaryAdapter):
                self._adapterCache[k] = adapter
                if (hasattr(adapter, "multiComponent") and
                    adapter.multiComponent):
                    self.addComponent(adapter)
            return adapter

    def __conform__(self, interface):
        return self.getComponent(interface)
    
    def upgradeToVersion1(self):
        # To let Componentized instances interact correctly with
        # rebuild(), we cannot use class objects as dictionary keys.
        for (k, v) in self._adapterCache.items():
            self._adapterCache[reflect.qual(k)] = v


class ReprableComponentized(Componentized):
    def __init__(self):
        Componentized.__init__(self)

    def __repr__(self):
        from cStringIO import StringIO
        from pprint import pprint
        sio = StringIO()
        pprint(self._adapterCache, sio)
        return sio.getvalue()

__all__ = ["Interface", "implements", "getInterfaces", "superInterfaces",
           "registerAdapter", "getAdapterClass", "getAdapter", "Componentized",
           "Adapter", "ReprableComponentized", "register"]
