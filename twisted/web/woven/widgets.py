# -*- test-case-name: twisted.test.test_woven -*-
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

# DOMWidgets

from __future__ import nested_scopes

import urllib
import warnings
from twisted.web.microdom import parseString, Element, Node
from twisted.web import domhelpers


#sibling imports
import model
import template
import view
import utils

from twisted.python import components, failure
from twisted.python import log
from twisted.internet import defer

viewFactory = view.viewFactory
document = parseString("<xml />")

missingPattern = document.createElement("div")
missingPattern.setAttribute("style", "border: dashed red 1px; margin: 4px")

"""
DOMWidgets are views which can be composed into bigger views.
"""

DEBUG = 0

_RAISE = 1

class Dummy:
    pass

class Widget(view.View):
    """
    A Widget wraps an object, its model, for display. The model can be a
    simple Python object (string, list, etc.) or it can be an instance
    of L{model.Model}.  (The former case is for interface purposes, so that
    the rest of the code does not have to treat simple objects differently
    from Model instances.)

    If the model is-a Model, there are two possibilities:

       - we are being called to enable an operation on the model
       - we are really being called to enable an operation on an attribute
         of the model, which we will call the submodel

    @cvar tagName: The tag name of the element that this widget creates. If this
          is None, then the original Node will be cloned.
    @cvar wantsAllNotifications: Indicate that this widget wants to recieve every
          change notification from the main model, not just notifications that affect
          its model.
    @ivar model: If the current model is an L{model.Model}, then the result of
          model.getData(). Otherwise the original object itself.
    """
    # wvupdate_xxx method signature: request, widget, data; returns None

    # Don't do lots of work setting up my stacks; they will be passed to me
    setupStacks = 0
    
    # Should we clear the node before we render the widget?
    clearNode = 0
    
    tagName = None
    def __init__(self, model = None, submodel = None, setup = None, controller = None, viewStack=None, *args, **kwargs):
        """
        @type model: L{interfaces.IModel}

        @param submodel: see L{Widget.setSubmodel}
        @type submodel: String

        @type setup: Callable
        """
        self.errorFactory = Error
        self.controller = controller
        self.become = None
        self._reset()
        view.View.__init__(self, model)
        self.node = None
        self.templateNode = None
        if submodel:
            self.submodel = submodel
        else:
            self.submodel = ""
        if setup:
            self.setupMethods = [setup]
        else:
            self.setupMethods = []
        self.viewStack = viewStack
        self.initialize(*args, **kwargs)

    def _reset(self):
        self.attributes = {}
        self.slots = {}
        self._children = []

    def initialize(self, *args, **kwargs):
        """
        Use this method instead of __init__ to initialize your Widget, so you
        don't have to deal with calling the __init__ of the superclass.
        """
        pass

    def setSubmodel(self, submodel):
        """
        I use the submodel to know which attribute in self.model I am responsible for
        """
        self.submodel = submodel

    def getData(self, request=None):
        """
        I have a model; however since I am a widget I am only responsible
        for a portion of that model. This method returns the portion I am
        responsible for.

        The return value of this may be a Deferred; if it is, then
        L{setData} will be called once the result is available.
        """
        return self.model.getData(request)

    def setData(self, request=None, data=None):
        """
        If the return value of L{getData} is a Deferred, I am called
        when the result of the Deferred is available.
        """
        self.model.setData(request, data)

    def add(self, item):
        """
        Add `item' to the children of the resultant DOM Node of this widget.

        @type item: A DOM node or L{Widget}.
        """
        self._children.append(item)

    def insert(self, index, item):
        """
        Insert `item' at `index' in the children list of the resultant DOM Node
        of this widget.

        @type item: A DOM node or L{Widget}.
        """
        self._children.insert(index, item)

    def setNode(self, node):
        """
        Set a node for this widget to use instead of creating one programatically.
        Useful for looking up a node in a template and using that.
        """
        # self.templateNode should always be the original, unmutated
        # node that was in the HTML template.
        if self.templateNode == None:
            self.templateNode = node
        self.node = node

    def cleanNode(self, node):
        """
        Do your part, prevent infinite recursion!
        """
        if node.hasAttribute('model'):
            node.removeAttribute('model')
        if node.hasAttribute('controller'):
            node.removeAttribute('controller')
        if node.hasAttribute('view'):
            node.removeAttribute('view')
        return node

    def generate(self, request, node):
        data = self.getData(request)
        if isinstance(data, defer.Deferred):
            data.addCallback(self.setDataCallback, request, node)
            data.addErrback(utils.renderFailure, request)
            return data
        return self._regenerate(request, node, data)

    def _regenerate(self, request, node, data):
        self._reset()
        self.setUp(request, node, data)
        for setupMethod in self.setupMethods:
            setupMethod(request, self, data)
        # generateDOM should always get a reference to the
        # templateNode from the original HTML
        result = self.generateDOM(request, self.templateNode or node)
        return result

    def setDataCallback(self, result, request, node):
        if isinstance(self.getData(request), defer.Deferred):
            self.setData(result)
        data = self.getData(request)
        if isinstance(data, defer.Deferred):
            import warnings
            warnings.warn("%r has returned a Deferred multiple times for the "
                          "same request; this is a potential infinite loop."
                          % self.getData)
            data.addCallback(self.setDataCallback, request, node)
            data.addErrback(utils.renderFailure, request)
            return data

        newNode = self._regenerate(request, node, result)
        returnNode = self.dispatchResult(request, node, newNode)
        if hasattr(self, 'outgoingId'):
            returnNode.setAttribute('id', self.outgoingId)
        self.handleNewNode(request, returnNode)
        self.handleOutstanding(request)
        if self.subviews:
            self.getTopModel().subviews.update(self.subviews)
        self.controller.domChanged(request, self, returnNode)
        return returnNode

    def setUp(self, request, node, data):
        """
        Override this method to set up your Widget prior to generateDOM. This
        is a good place to call methods like L{add}, L{insert}, L{__setitem__}
        and L{__getitem__}.

        Overriding this method obsoletes overriding generateDOM directly, in
        most cases.

        @type request: L{twisted.web.server.Request}.
        @param node: The DOM node which this Widget is operating on.
        @param data: The Model data this Widget is meant to operate upon.
        """
        pass

    def generateDOM(self, request, node):
        """
        @returns: A DOM Node to replace the Node in the template that this
                  Widget handles. This Node is created based on L{tagName},
                  L{children}, and L{attributes} (You should populate these
                  in L{setUp}, probably).
        """
        if self.become:
            #print "becoming"
            become = self.become
            self.become = None
            parent = node.parentNode
            node.parentNode = None
            old = node.cloneNode(1)
            node.parentNode = parent
            gen = become.generateDOM(request, node)
            if old.attributes.has_key('model'):
                del old.attributes['model']
            old.removeAttribute('controller')
            gen.appendChild(old)
            self.node = gen
            return gen
        if DEBUG:
            template = node.toxml()
            log.msg(template)
        if not self.tagName:
            self.tagName = self.templateNode.tagName
        if node is not self.templateNode or self.tagName != self.templateNode.tagName:
            parent = node.parentNode
            node = document.createElement(self.tagName)
            node.parentNode = parent
        else:
            parentNode = node.parentNode
            node.parentNode = None
            if self.clearNode:
                new = node.cloneNode(0)
            else:
                new = node.cloneNode(1)
            node.parentNode = parentNode
            node = self.cleanNode(new)
        #print "NICE CLEAN NODE", node.toxml(), self._children
        for key, value in self.attributes.items():
            node.setAttribute(key, value)
        for item in self._children:
            if hasattr(item, 'generate'):
                parentNode = node.parentNode
                node.parentNode = None
                item = item.generate(request, node.cloneNode(1))
                node.parentNode = parentNode
            node.appendChild(item)
        #print "WE GOT A NODE", node.toxml()
        self.node = node
        return self.node

    def modelChanged(self, payload):
        request = payload.get('request', None)
        if request is None:
            request = Dummy()
            request.d = document
        oldNode = self.node
        if payload.has_key(self.submodel):
            data = payload[self.submodel]
        else:
            data = self.getData(request)
        newNode = self._regenerate(request, oldNode, data)
        returnNode = self.dispatchResult(request, oldNode, newNode)
        # shot in the dark: this seems to make *my* code work.  probably will
        # break if returnNode returns a Deferred, as it's supposed to be able
        # to do -glyph
#        self.viewStack.push(self)
#        self.controller.controllerStack.push(self.controller)
        self.handleNewNode(request, returnNode)
        self.handleOutstanding(request)
        self.controller.domChanged(request, self, returnNode)

    def __setitem__(self, item, value):
        """
        Convenience syntax for adding attributes to the resultant DOM Node of
        this widget.
        """
        assert value is not None
        self.attributes[item] = value

    def __getitem__(self, item):
        """
        Convenience syntax for getting an attribute from the resultant DOM Node
        of this widget.
        """
        return self.attributes[item]

    def setError(self, request, message):
        """
        Convenience method for allowing a Controller to report an error to the
        user. When this is called, a Widget of class self.errorFactory is instanciated
        and set to self.become. When generate is subsequently called, self.become
        will be responsible for mutating the DOM instead of this widget.
        """
        #print "setError called", self
        id = self.attributes.get('id', '')
        
        self.become = self.errorFactory(self.model, message)
        self.become['id'] = id
#        self.modelChanged({'request': request})

    def getTopModel(self):
        """Get a reference to this page's top model object.
        """
        top = self.model
        while top.parent is not None:
            top = top.parent
        return top

    def getPattern(self, name, default=missingPattern, clone=1, deep=1):
        """Get a named slot from the incoming template node. Returns a copy
        of the node and all its children. If there was more than one node with
        the same slot identifier, they will be returned in a round-robin fashion.
        """
        #print self.templateNode.toxml()
        if self.slots.has_key(name):
            slots = self.slots[name]
        else:
            sm = self.submodel.split('/')[-1]
            slots = domhelpers.locateNodes(self.templateNode, name + 'Of', sm)
            if not slots:
                slots = domhelpers.locateNodes(self.templateNode, "pattern", name, noNesting=1)
                if not slots:
                    msg = 'WARNING: No template nodes were found '\
                              '(tagged %s="%s"'\
                              ' or pattern="%s") for node %s (full submodel path %s)' % (name + "Of",
                                            sm, name, self.templateNode, `self.submodel`)
                    if default is _RAISE:
                        raise Exception(msg)
                    if DEBUG:
                        warnings.warn(msg)
                    if default is missingPattern:
                        newNode = missingPattern.cloneNode(1)
                        newNode.appendChild(document.createTextNode(msg))
                        return newNode
                    return default
            self.slots[name] = slots
        slot = slots.pop(0)
        slots.append(slot)
        if clone:
            parentNode = slot.parentNode
            slot.parentNode = None
            clone = slot.cloneNode(deep)
            slot.parentNode = parentNode
            return clone
        return slot

    def addUpdateMethod(self, updateMethod):
        """Add a method to this widget that will be called when the widget
        is being rendered. The signature for this method should be
        updateMethod(request, widget, data) where widget will be the
        instance you are calling addUpdateMethod on.
        """
        self.setupMethods.append(updateMethod)

    def addEventHandler(self, eventName, handler, *args):
        """Add an event handler to this widget. eventName is a string
        indicating which javascript event handler should cause this
        handler to fire. Handler is a callable that has the signature
        handler(request, widget, *args).
        """
        def handlerUpdateStep(request, widget, data):
            extraArgs = ''
            for x in args:
                extraArgs += " ,'" + x.replace("'", "\\'") + "'"
            widget[eventName] = "woven_eventHandler('%s', this%s); return false" % (eventName, extraArgs)
            setattr(self, 'wevent_' + eventName, handler)
        self.addUpdateMethod(handlerUpdateStep)
        
    def onEvent(self, request, eventName, *args):
        """Dispatch a client-side event to an event handler that was
        registered using addEventHandler.
        """
        eventHandler = getattr(self, 'wevent_' + eventName, None)
        if eventHandler is None:
            raise NotImplementedError("A client side '%s' event occured,"
                    " but there was no event handler registered on %s." % 
                    (eventName, self))
                
        eventHandler(request, self, *args)


class DefaultWidget(Widget):
    def generate(self, request, node):
        """
        By default, we just return the node unchanged
        """
        if self.become:
            become = self.become
            self.become = None
            parent = node.parentNode
            node.parentNode = None
            old = node.cloneNode(1)
            node.parentNode = parent
            gen = become.generateDOM(request, node)
            del old.attributes['model']
            gen.appendChild(self.cleanNode(old))
            return gen
        return node

    def modelChanged(self, payload):
        """We're not concerned if the model has changed.
        """
        pass


class Text(Widget):
    """
    A simple Widget that renders some text.
    """
    def __init__(self, text, raw=0, clear=1, *args, **kwargs):
        """
        @param text: The text to render.
        @type text: A string or L{model.Model}.
        @param raw: A boolean that specifies whether to render the text as
              a L{domhelpers.RawText} or as a DOM TextNode.
        """
        self.raw = raw
        self.clear = clear
        if isinstance(text, model.Model):
            Widget.__init__(self, text, *args, **kwargs)
        else:
            Widget.__init__(self, model.Model(), *args, **kwargs)
        self.text = text

    def generateDOM(self, request, node):
        if node and self.clear:
            domhelpers.clearNode(node)
        if isinstance(self.text, model.Model):
            if self.raw:
                textNode = domhelpers.RawText(str(self.getData(request)))
            else:
                textNode = document.createTextNode(str(self.getData(request)))
            if node is None:
                return textNode
            node.appendChild(textNode)
            return node
        else:
            if self.raw:
                return domhelpers.RawText(self.text)
            else:
                return document.createTextNode(self.text)


class Image(Text):
    """
    A simple Widget that creates an `img' tag.
    """
    tagName = 'img'
    border = '0'
    def generateDOM(self, request, node):
        #`self.text' is lame, perhaps there should be a DataWidget that Text
        #and Image both subclass.
        node.setAttribute('border', self.border)
        if isinstance(self.text, model.Model):
            data = self.getData(request)
        else:
            data = self.text
        assert data is not None, "data is None, self.text is %r" % (self.text,)
        node = Widget.generateDOM(self, request, node)
        node.setAttribute('src', data)
        return node


class Error(Widget):
    tagName = 'span'
    def __init__(self, model, message="", *args, **kwargs):
        Widget.__init__(self, model, *args, **kwargs)
        self.message = message

    def generateDOM(self, request, node):
        self['style'] = 'color: red'
        self.add(Text(" " + self.message))
        return Widget.generateDOM(self, request, node)


class Div(Widget):
    tagName = 'div'


class Span(Widget):
    tagName = 'span'


class Br(Widget):
    tagName = 'br'


class Input(Widget):
    tagName = 'input'
    def setSubmodel(self, submodel):
        self.submodel = submodel
        self['name'] = submodel

    def generateDOM(self, request, node):
        if not self.attributes.has_key('name') and not node.getAttribute('name'):
            if self.submodel:
                id = self.submodel
            else:
                id = self.attributes.get('id', node.getAttribute('id'))
            self['name'] = id
        mVal = self.getData(request)
        if mVal is None:
            mVal = ''
        assert mVal is not None
        if not self.attributes.has_key('value'):
            self['value'] = str(mVal)
        return Widget.generateDOM(self, request, node)


class CheckBox(Input):
    def initialize(self):
        self['type'] = 'checkbox'


class RadioButton(Input):
    def initialize(self):
        self['type'] = 'radio'


class File(Input):
    def initialize(self):
        self['type'] = 'file'


class Hidden(Input):
    def setUp(self, request, node, m):
        self['type'] = 'hidden'


class InputText(Input):
    def initialize(self):
        self['type'] = 'text'


class PasswordText(Input):
    """
    I render a password input field.
    """
    def initialize(self):
        self['type'] = 'password'


class Button(Input):
    def initialize(self):
        self['type'] = 'button'


class Select(Input):
    tagName = 'select'


class Option(Input):
    tagName = 'option'
    def initialize(self):
        self.text = ''

    def setText(self, text):
        """
        Set the text to be displayed within the select menu.
        """
        self.text = text

    def setValue(self, value):
        self['value'] = str(value)

    def generateDOM(self, request, node):
        self.add(Text(self.text or self.getData(request)))
        return Input.generateDOM(self, request, node)


class Anchor(Widget):
    tagName = 'a'
    trailingSlash = ''
    def initialize(self):
        self.baseHREF = ''
        self.parameters = {}
        self.raw = 0
        self.text = ''

    def setRaw(self, raw):
        self.raw = raw

    def setLink(self, href):
        self.baseHREF= href

    def setParameter(self, key, value):
        self.parameters[key] = value

    def setText(self, text):
        self.text = text

    def generateDOM(self, request, node):
        href = self.baseHREF
        params = urllib.urlencode(self.parameters)
        if params:
            href = href + '?' + params
        data = self.getData(request)
        self['href'] = href or str(data) + self.trailingSlash
        #self['href'] = urllib.quote(self['href'])
        if data is None:
            data = ""
        self.add(Text(self.text or data, self.raw, 0))
        return Widget.generateDOM(self, request, node)


class SubAnchor(Anchor):
    def generateDOM(self, request, node):
        href = self.baseHREF
        params = urllib.urlencode(self.parameters)
        if params:
            href = href + '?' + params
        data = self.getData(request)
        if not href:
            href = node.getAttribute('href')
        self['href'] = href + str(data) + self.trailingSlash
        if data is None:
            data = ""
        self.add(Text(self.text or data, self.raw, 0))
        return Widget.generateDOM(self, request, node)



class DirectoryAnchor(Anchor):
    trailingSlash = '/'


def appendModel(newNode, modelName):
    if newNode is None: return
    curModel = newNode.getAttribute('model')
    if curModel is None:
        newModel = str(modelName)
    else:
        newModel = str(modelName) + '/' + curModel
    newNode.setAttribute('model', newModel)


class List(Widget):
    """
    I am a widget which knows how to generateDOM for a python list.

    A List should be specified in the template HTML as so::

       | <ul model="blah" view="List">
       |     <li pattern="emptyList">This will be displayed if the list
       |         is empty.</li>
       |     <li pattern="listItem" view="Text">Foo</li>
       | </ul>

    If you have nested lists, you may also do something like this::

       | <table model="blah" view="List">
       |     <tr pattern="listHeader"><th>A</th><th>B</th></tr>
       |     <tr pattern="emptyList"><td colspan='2'>***None***</td></tr>
       |     <tr pattern="listItem">
       |         <td><span view="Text" model="1" /></td>
       |         <td><span view="Text" model="2" /></td>
       |     </tr>
       |     <tr pattern="listFooter"><td colspan="2">All done!</td></tr>
       | </table>

    Where blah is the name of a list on the model; eg::

       | self.model.blah = ['foo', 'bar']

    """
    tagName = None
    defaultItemView = "DefaultWidget"
    def generateDOM(self, request, node):
        node = Widget.generateDOM(self, request, node)
        listHeader = self.getPattern('listHeader', None)
        listFooter = self.getPattern('listFooter', None)
        emptyList = self.getPattern('emptyList', None)
        domhelpers.clearNode(node)
        if not listHeader is None:
            node.appendChild(listHeader)
        data = self.getData(request)
        if data:
            self._iterateData(node, self.submodel, data)
        elif not emptyList is None:
            node.appendChild(emptyList)
        if not listFooter is None:
            node.appendChild(listFooter)
        return node

    def _iterateData(self, parentNode, submodel, data):
        currentListItem = 0
        for itemNum in range(len(data)):
            # theory: by appending copies of the li node
            # each node will be handled once we exit from
            # here because handleNode will then recurse into
            # the newly appended nodes

            newNode = self.getPattern('listItem')
            seq = domhelpers.getIfExists(newNode,'listIndex')
            if seq:
                seq.setAttribute('value',str(itemNum))
            appendModel(newNode, itemNum)
            if not newNode.getAttribute("view"):
                newNode.setAttribute("view", self.defaultItemView)
            parentNode.appendChild(newNode)


class KeyedList(List):
    """
    I am a widget which knows how to display the values stored within a
    Python dictionary..

    A KeyedList should be specified in the template HTML as so::

       | <ul model="blah" view="KeyedList">
       |     <li pattern="emptyList">This will be displayed if the list is
       |         empty.</li>
       |     <li pattern="keyedListItem" view="Text">Foo</li>
       | </ul>

    I can take advantage of C{listHeader}, C{listFooter} and C{emptyList}
    items just as a L{List} can.
    """
    def _iterateData(self, parentNode, submodel, data):
        """
        """
        currentListItem = 0
        keys = data.keys()
        # Keys may be a tuple, if this is not a true dictionary but a dictionary-like object
        if hasattr(keys, 'sort'):
            keys.sort()
        for key in keys:
            newNode = self.getPattern('keyedListItem')
            if not newNode:
                newNode = self.getPattern('item', _RAISE)
                if newNode:
                    warnings.warn("itemOf= is deprecated, "
                                        "please use listItemOf instead",
                                        DeprecationWarning)

            appendModel(newNode, key)
            if not newNode.getAttribute("view"):
                newNode.setAttribute("view", "DefaultWidget")
            parentNode.appendChild(newNode)


class ColumnList(Widget):
    def __init__(self, model, columns=1, start=0, end=0, *args, **kwargs):
        Widget.__init__(self, model, *args, **kwargs)
        self.columns = columns
        self.start = start
        self.end = end

    def setColumns(self, columns):
        self.columns = columns

    def setStart(self, start):
        self.start = start

    def setEnd(self, end):
        self.end = end

    def setUp(self, request, node, data):
        pattern = self.getPattern('columnListRow', clone=0)
        if self.end:
            listSize = self.end - self.start
            if listSize > len(data):
                listSize = len(data)
        else:
            listSize = len(data)
        for itemNum in range(listSize):
            if itemNum % self.columns == 0:
                row = self.getPattern('columnListRow')
                domhelpers.clearNode(row)
                node.appendChild(row)

            newNode = self.getPattern('columnListItem')

            appendModel(newNode, itemNum + self.start)
            if not newNode.getAttribute("view"):
                newNode.setAttribute("view", "DefaultWidget")
            row.appendChild(newNode)
        node.removeChild(pattern)
        return node


class Bold(Widget):
    tagName = 'b'


class Table(Widget):
    tagName = 'table'


class Row(Widget):
    tagName = 'tr'


class Cell(Widget):
    tagName = 'td'


class RawText(Widget):
    def generateDOM(self, request, node):
        self.node = domhelpers.RawText(self.getData(request))
        return self.node

from types import StringType

class Link(Widget):
    """A utility class for generating <a href='foo'>bar</a> tags.
    """

    def setUp(self, request, node, data):
        # TODO: we ought to support Deferreds here for both text and href!
        if isinstance(data, StringType):
            node.tagName = 'a'
            node.setAttribute("href", data)
        else:
            data = self.model
            txt = data.getSubmodel("text").getData(request)
            if not isinstance(txt, Node):
                txt = document.createTextNode(txt)
            lnk = data.getSubmodel("href").getData(request)
            self['href'] = lnk
            node.tagName = 'a'
            domhelpers.clearNode(node)
            node.appendChild(txt)


view.registerViewForModel(Text, model.StringModel)
view.registerViewForModel(List, model.ListModel)
view.registerViewForModel(KeyedList, model.DictionaryModel)
view.registerViewForModel(Link, model.Link)
