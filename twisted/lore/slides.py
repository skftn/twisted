# Twisted, the Framework of Your Internet
# Copyright (C) 2001-2002 Matthew W. Lefkowitz
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
"""Rudimentary slide support for Lore.

TODO:
    - Complete mgp output target 
        - syntax highlighting
        - saner font handling
        - probably lots more
    - Add HTML output targets
        - one slides per page (with navigation links)
        - all in one page

Example input file:
<html>

<head><title>Title of talk</title></head>

<body>
<h1>Title of talk</h1>

<h2>First Slide</h2>

<ul>
  <li>Bullet point</li>
  <li>Look ma, I'm <strong>bold</strong>!</li>
  <li>... etc ...</li>
</ul>


<h2>Second Slide</h2>

<pre class="python">
# Sample code sample.
print "Hello, World!"
</pre>

</body>

</html>
"""
from __future__ import nested_scopes

from twisted.lore import default
from twisted.web import domhelpers, microdom
# These should be factored out
from twisted.lore.latex import BaseLatexSpitter, processFile, getLatexText
from twisted.lore.tree import getHeaders

import os, os.path
from cStringIO import StringIO

entities = { 'amp': '&', 'gt': '>', 'lt': '<', 'quot': '"',
             'copy': '(c)'}

class MagicpointOutput(BaseLatexSpitter):
    def writeNodeData(self, node):
        buf = StringIO()
        getLatexText(node, buf.write, entities=entities)
        self.writer(buf.getvalue())

    def visitNode_title(self, node):
        self.title = domhelpers.getNodeText(node)

    def visitNode_body(self, node):
        # Adapted from tree.generateToC
        self.fontStack = [('standard', None)]

        self.writer(self.start_h2)
        self.writer(self.title)
        self.writer(self.end_h2)

        for element in getHeaders(node):
            level = int(element.tagName[1])-1
            self.writer(level * '\t')
            self.writer(domhelpers.getNodeText(element))
            self.writer('\n')

        self.visitNodeDefault(node)

    def visitNode_pre(self, node):
        # TODO: Syntax highlighting
        text = domhelpers.getNodeText(node)
        lines = text.split('\n')
        self.writer('%font "typewriter", size 4\n')
        self.fontStack.append(('typewriter', 4))
        for line in lines:
            self.writer(' ' + line + '\n')
        del self.fontStack[-1]
        self.writer('%' + self.fontName() + '\n')

    def visitNode_strong(self, node):
        self.doFont(node, 'bold')

    def visitNode_em(self, node):
        self.doFont(node, 'italic')

    def visitNode_code(self, node):
        self.doFont(node, 'typewriter')

    def doFont(self, node, style):
        self.fontStack.append((style, None))
        self.writer('\n%cont, ' + self.fontName() + '\n')
        self.visitNodeDefault(node)
        del self.fontStack[-1]
        self.writer('\n%cont, ' + self.fontName() + '\n')

    def fontName(self):
        names = [x[0] for x in self.fontStack]
        if 'typewriter' in names:
            name = 'typewriter'
        else:
            name = ''

        if 'bold' in names:
            name += 'bold'
        if 'italic' in names:
            name += 'italic'

        if name == '':
            name = 'standard'

        sizes = [x[1] for x in self.fontStack]
        sizes.reverse()
        for size in sizes:
            if size:
                return 'font "%s" size %d' % (name, size)

        return 'font "%s"' % name

    start_h2 = "%page\n\n"
    end_h2 = '\n\n%font "typewriter", size 2\n\n%font "standard"\n'

    start_li = "\t"
    end_li = "\n"
    

def convertFile(filename, outputter, template, ext=".mgp"):
    fout = open(os.path.splitext(filename)[0]+ext, 'w')
    fout.write(open(template).read())
    spitter = outputter(fout.write, os.path.dirname(filename), filename)
    fin = open(filename)
    processFile(spitter, fin)
    fin.close()
    fout.close()


# HTML DOM tree stuff

def splitIntoSlides(document):
    body = domhelpers.findNodesNamed(document, 'body')[0]
    slides = []
    slide = []
    title = '(unset)'
    for child in body.childNodes:
        if isinstance(child, microdom.Element) and child.tagName == 'h2':
            if slide:
                slides.append((title, slide))
                slide = []
            title = domhelpers.getNodeText(child)
        else:
            slide.append(child)
    slides.append((title, slide))
    return slides

def insertPrevNextLinks(slides, filename, ext):
    for slide in slides:
        for name, offset in (("previous", -1), ("next", +1)):
            if (slide.pos > 0 and name == "previous") or \
               (slide.pos < len(slides)-1 and name == "next"):
                for node in domhelpers.findElementsWithAttribute(slide.dom, "class", name):
                    node.appendChild(microdom.Text(slides[slide.pos+offset].title))
                    node.setAttribute('href', '%s-%d%s' 
                                      % (filename[0], slide.pos+offset, ext))
            else:
                for node in domhelpers.findElementsWithAttribute(slide.dom, "class", name):
                    pos = 0
                    for child in node.parentNode.childNodes:
                        if child is node:
                            del node.parentNode.childNodes[pos]
                            break
                        pos += 1


class HTMLSlide:
    def __init__(self, dom, title, pos):
        self.dom = dom
        self.title = title
        self.pos = pos


def munge(document, template, linkrel, d, fullpath, ext, url):
    # FIXME: This has *way* to much duplicated crap in common with tree.munge
    from tree import removeH1, expandAPI, fixAPI, fontifyPython, \
                     addPyListings, addHTMLListings, setTitle
    #fixRelativeLinks(template, linkrel)
    removeH1(document)
    expandAPI(document)
    fixAPI(document, url)
    fontifyPython(document)
    addPyListings(document, d)
    addHTMLListings(document, d)
    #fixLinks(document, ext)
    #putInToC(template, generateToC(document))
    template = template.cloneNode(1)

    # Insert the slides into the template
    slides = []
    pos = 0
    for title, slide in splitIntoSlides(document):
        t = template.cloneNode(1)
        setTitle(t, [microdom.Text(title)])
        tmplbody = domhelpers.findElementsWithAttribute(t, "class", "body")[0]
        tmplbody.childNodes = slide
        tmplbody.setAttribute("class", "content")
        # FIXME: Next/Prev links
        # FIXME: Perhaps there should be a "Template" class?  (setTitle/setBody
        #        could be methods...)
        slides.append(HTMLSlide(t, title, pos))
        pos += 1

    insertPrevNextLinks(slides, os.path.splitext(os.path.basename(fullpath)), ext)
    
    return slides


def doFile(fn, linkrel, ext, url, templ):
    from tree import parseFileAndReport
    doc = parseFileAndReport(fn)
    slides = munge(doc, templ, linkrel, os.path.dirname(fn), fn, ext, url)
    for slide, index in zip(slides, range(len(slides))):
        slide.dom.writexml(open(os.path.splitext(fn)[0]+'-'+str(index)+ext, 'wb'))


class SlidesProcessingFunctionFactory(default.ProcessingFunctionFactory):
    doFile = [doFile]

    def generate_mgp(self, d):
        template = d.get('template', 'template.mgp')
        df = lambda file, linkrel: convertFile(file, MagicpointOutput, template, ext=".mgp")
        return df

factory=SlidesProcessingFunctionFactory()

