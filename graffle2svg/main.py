#!/usr/bin/env python3
#Copyright (c) 2009, Tim Wintle
#Copyright (c) 2015, Tim Wintle, Stephane Galland
#All rights reserved.
#
#Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#    * Neither the name of the project nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

#THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from io import BufferedReader
from typing import Dict, Union
import xml.dom.minidom

from .rtf import extractRTFString
from .styles import CascadingStyles
from . import geom
from . import fileinfo


class GraffleParser:

    def __init__(self):
        self.doc_dict = None
        self.g_dom = None

    def walk_graffle_file(self, filename: Union[str, BufferedReader]) -> Dict:
        import plistlib
        if isinstance(filename, BufferedReader):
            self.doc_dict = plistlib.load(filename)
        else:
            with open(filename, 'r') as fp:
                self.doc_dict = plistlib.load(fp)
        if self.doc_dict is None:
            raise Exception('File not found or not Plist format')
        return self.doc_dict

    def walk_graffle(self, xmlstr, **kwargs):
        """Walk over the file."""
        self.g_dom = xml.dom.minidom.parseString(xmlstr)

        self.walk_graffle_doc(self.g_dom, **kwargs)

    def walk_graffle_doc(self, parent):
        # want to pass this around like a continuation
        cont = self.node_list_gen(parent.childNodes)
        for e in cont:
            if e.nodeType == e.DOCUMENT_TYPE_NODE:
                pass
            localname = e.localName

            if localname == 'plist':
                # Apple's main container
                self.walk_graffle_doc(e)

            if localname == 'dict':
                self.doc_dict = self.return_graffle_dict(e)

    def node_list_gen(self, nodelist):
        """We need this so we can pass continuations around"""
        for e in nodelist:
            yield e

    def return_graffle_node(self, parent):
        """Return a python representation of the node passed"""
        if parent.nodeType == parent.TEXT_NODE:
            return parent.wholeText
        elif parent.localName == 'dict':
            return self.return_graffle_dict(parent)
        elif parent.localName == 'array':
            return self.return_graffle_array(parent)
        elif parent.localName == 'true':
            return True
        elif parent.localName == 'false':
            return False
        elif parent.localName in ['string', 'real', 'integer']:
            return self.return_graffle_node(parent.firstChild)
        return parent.nodeType

    def return_graffle_dict(self, parent):
        """Graffle has dicts like
            <dict>
                <key />
                <integer />
                <key />
                <string />
            </dict>
            - pass the <dict> node to this method
        """
        retdict = {}
        cont = self.node_list_gen(parent.childNodes)
        key, val = None, None
        for e in cont:
            if e.nodeType == e.TEXT_NODE:
                continue
            localname = e.localName
            if localname == 'key':
                key = self.return_graffle_node(e.firstChild)
            else:
                val = self.return_graffle_node(e)
                retdict[key] = val
        return retdict

    def return_graffle_array(self, parent):
        """Graffle has arrays like
            <array>
                <string />
                <string />
            </array>
            - pass the <array> node to this method
        """
        retlist = []
        cont = self.node_list_gen(parent.childNodes)
        for e in cont:
            if e.nodeType == e.TEXT_NODE:
                continue
            retlist.append(self.return_graffle_node(e))
        return retlist


class GraffleInterpreter:
    __slots__ = ['doc_dict', 'target', 'fileinfo', 'imagelist', 'bounding_box']

    def __init__(self):
        self.doc_dict = None
        self.fileinfo = None
        self.target = None
        self.imagelist = None
        self.bounding_box = None

    def set_target(self, target):
        self.target = target

    def getdict(self):
        return self.doc_dict

    def setdict(self, doc_dict):
        self.doc_dict = doc_dict
        self.fileinfo = None
        self.imagelist = None
        if self.doc_dict is not None:
            # Extract file information
            self.fileinfo = fileinfo.FileInfo(self.doc_dict)
            # Graffle lists it's image references separately
            self.imagelist = self.doc_dict.get('ImageList',[])

    dict = property(getdict, setdict, doc ='internal graffle dictionary')

    def parse_coords(self, s):
        """in: "{0,1}" -> [0,1]"""
        return [float(a) for a in s[1:-1].split(',')]

    def extract_magnet_coordinates(self, mgnts):
        return [self.parse_coords(a) for a in mgnts]

    def extract_bound_coordinates(self, bnds):
        bnds = bnds[1:-1].strip()
        bnds = bnds.split(',')
        coords = []
        for bnd in bnds:
            bnd = bnd.replace('{', '')
            bnd = bnd.replace('}', '')
            coords.append(float(bnd))
        return coords

    def extract_page(self, page=0,  background=True, bounding_box=None):
        if self.doc_dict.get('Sheets') is not None:
            mydict = self.doc_dict['Sheets'][page]
        else:
            mydict = self.doc_dict

        if background:
            if self.fileinfo.fmt_version >= 6:
                # Graffle version 6 has a background graphic
                background = mydict['BackgroundGraphic']
                # draw this
                self.iterate_graffle_graphics([background])
            elif self.fileinfo.fmt_version < 6:
                # Version 5 has a CanvasColor property instead
                colour = mydict.get('CanvasColor')
                if colour is not None:
                    # We have to guess the document's dimensions from the print
                    # size
                    # - these numbers appear to match up with the background
                    # size in version 6.
                    origin = self.parse_coords(mydict.get('CanvasOrigin', '{0,0}'))
                    print_info = self.fileinfo.printinfo
                    paper_size = print_info.paper_size
                    Lmargin = print_info.left_margin
                    Rmargin = print_info.right_margin
                    Tmargin = print_info.top_margin
                    Bmargin = print_info.bottom_margin
                    x, y = origin
                    width = paper_size[0] - Lmargin - Rmargin
                    height = paper_size[1] - Bmargin - Tmargin
                    self.target.add_rect(x=x,
                                         y=y,
                                         width=width,
                                         height=height,
                                         rx=None,
                                         ry=None)
        self.bounding_box = bounding_box
        graphics = reversed(mydict['GraphicsList'])
        self.target.reset()
        self.iterate_graffle_graphics(graphics)
        self.target.add_requirements()
        self.target.add_document_bounds()

    def svg_add_graffle_shaped_graphic(self, graphic):
        shape = graphic['Shape']

        extra_opts = {}
        if graphic.get('HFlip', 'NO') == 'YES':
            extra_opts['HFlip'] = True
        if graphic.get('VFlip', 'NO') == 'YES':
            extra_opts['VFlip'] = True
        if graphic.get('Rotation') is not None:
            extra_opts['Rotation'] = float(graphic['Rotation'])
        extra_opts['id'] = str(graphic['ID'])

        coords = self.extract_bound_coordinates(graphic['Bounds'])

        if geom.out_of_boundingbox(((coords[0], coords[1]),
                                    ((coords[0]+coords[2]),
                                     (coords[1] + coords[3]))),
                                   self.bounding_box):
            return False
        if shape == 'Rectangle':
            if graphic.get('ImageID') is not None:
                # TODO: images
                image_id = graphic['ImageID']
                if len(self.imagelist) <= image_id:
                    print('Error - image out of range')
                    return
                image = self.imagelist[image_id]
                self.target.add_image(bounds=coords, href=image)
                print(f'Insert Image - {image}')
            else:
                # radius of corners is stored on the style in graffle
                sty = graphic.get('Style', {})
                stroke = sty.get('stroke', {})
                radius = stroke.get('CornerRadius', None)

                x, y = coords[0], coords[1]
                width = coords[2]  # - coords[0]
                height = coords[3]  # - coords[1]
                self.target.add_rect(
                                     x=x,
                                     y=y,
                                     width=width,
                                     height=height,
                                     rx=radius,
                                     ry=radius,
                                     **extra_opts)

        elif shape == 'RoundRect':
            sty = graphic.get('Style', {})
            stroke = sty.get('stroke', {})
            radius = stroke.get('CornerRadius', None)

            x, y = coords[0], coords[1]
            width = coords[2]  # - coords[0]
            height = coords[3]  # - coords[1]
            import math
            self.target.add_rect(
                                 x=x,
                                 y=y,
                                 width=width,
                                 height=height,
                                 rx=(width - math.sqrt(width**2-height**2))/2,
                                 ry=height/2,
                                 **extra_opts)
        elif shape == 'HorizontalTriangle':
            self.target.add_horizontal_triangle(
                                                bounds=coords,
                                                **extra_opts)
        elif shape == 'RightTriangle':
            self.target.add_right_triangle(
                                           bounds=coords,
                                           **extra_opts)
        elif shape == 'VerticalTriangle':
            self.target.add_vertical_triangle(
                                              bounds=coords,
                                              **extra_opts)
        elif shape == 'Circle':
            # Actually can be an ellipse
            self.target.add_ellipse(
                                    bounds=coords,
                                    **extra_opts)
        elif shape == 'AdjustableArrow':
            self.target.add_adjustable_arrow(
                                           bounds=coords,
                                           graphic=graphic,
                                           **extra_opts)
        elif shape == 'Diamond':
            self.target.add_diamond(
                                   bounds=coords,
                                   graphic=graphic,
                                   **extra_opts)
        elif shape == 'Cloud':
            self.target.add_cloud(bounds=coords,
                                  graphic=graphic,
                                  **extra_opts)
        else:
            print(f"Don't know how to display Shape {(graphic['Shape'])}")

        return True

    def iterate_graffle_graphics(self, graphics_list):
        """parent should be a list of """
        for graphics in graphics_list:
            # Styling
            self.target.style.appendScope()
            if graphics.get('Style') is not None:
                self.target.set_graffle_style(graphics.get('Style'))

            cls = graphics['Class']
            if cls == 'SolidGraphic':
                # used as background - add a
                shallowcopy = dict({'Shape': 'Rectangle'})
                shallowcopy.update(graphics)
                self.svg_add_graffle_shaped_graphic(shallowcopy)

            elif cls == 'ShapedGraphic':
                try:
                    if not self.svg_add_graffle_shaped_graphic(graphics):
                        continue
                except:
                    raise
                    print('could not show shaped graphic')

            elif cls == 'LineGraphic':
                pts = self.extract_magnet_coordinates(graphics['Points'])
                if geom.out_of_boundingbox(pts, self.bounding_box):
                    continue
                self.target.style['fill'] = 'none'
                if not graphics.get('OrthogonalBarAutomatic'):
                    bar_pos = graphics.get('OrthogonalBarPosition')
                    if bar_pos is not None:
                        # Decide where to place the orthogonal position

                        bar_pos = float(bar_pos)
                        """
                        # This isn't right
                        out_pts = []
                        i = 0
                        while i < len(pts) - 1:
                            p1 = pts[i]
                            p2 = pts[i+1]
                            newpt = [p1[0] + bar_pos, p1[1]]
                            out_pts.append(p1)
                            out_pts.append(newpt)
                            out_pts.append(p2)
                            i+=2
                        pts = out_pts
                        """

                    self.target.add_path(pts, id=str(graphics['ID']))

            elif cls == 'TableGroup':
                # In Progress
                table_graphics = graphics.get('Graphics')
                if table_graphics is not None:
                    self.target.add_layer(self, reversed(table_graphics))

            elif cls == 'Group':
                subgraphics = graphics.get('Graphics')
                if subgraphics is not None:
                    self.target.add_layer(self, reversed(subgraphics))
            else:
                print(f"Don't know how to display Class \"{cls}\"")

            if graphics.get('Text') is not None:
                # have to write some text too ...
                self.target.set_graffle_font(graphics.get('FontInfo'))
                coords = self.extract_bound_coordinates(graphics['Bounds'])

                if geom.out_of_boundingbox(((coords[0], coords[1]),
                                            ((coords[0] + coords[2]),
                                             (coords[1] + coords[3]))),
                                           self.bounding_box):
                    continue
                x, y, width, height = coords
                dx = float(graphics['Text'].get('Pad', 0))
                dy = float(graphics['Text'].get('VerticalPad', 0))
                self.target.add_text(
                                     rtftext=graphics.get('Text').get('Text', ''),
                                     x=x+dx,
                                     y=y+dy,
                                     width=width-2*dx,
                                     height=height-2*dy,
                                     fontinfo=graphics.get('FontInfo'),
                                     id=graphics['ID'])

            self.target.style.popScope()


class TargetSvg:
    def __init__(self):
        self.svg_bounds = None
        self.svg_dom = None
        self.svg_current_layer = None
        self.svg_current_font = ''
        self.svg_tag = None
        self.svg_graphroot = None
        self.svg_def = None
        self.style = None
        self.reset()

    def __bb_box(self, minx, miny, w, h):
        maxx = minx + w
        maxy = miny + h
        if not self.svg_bounds:
            self.svg_bounds = (minx, miny, maxx, maxy)
        else:
            (ix, iy, ax, ay) = self.svg_bounds
            if minx < ix:
                ix = minx
            if miny < iy:
                iy = miny
            if maxx > ax:
                ax = maxx
            if maxy > ay:
                ay = maxy
            self.svg_bounds = (ix, iy, ax, ay)

    def __bb_point(self, px, py):
        if not self.svg_bounds:
            self.svg_bounds = (px, py, px, py)
        else:
            (ix, iy, ax, ay) = self.svg_bounds
            if px < ix:
                ix = px
            if py < iy:
                iy = py
            if px > ax:
                ax = px
            if py > ay:
                ay = py
            self.svg_bounds = (ix, iy, ax, ay)

    def reset(self):
        self.svg_bounds = None
        self.svg_dom = xml.dom.minidom.Document()
        self.svg_dom.doctype = ''
        self.svg_tag = self.svg_dom.createElement('svg')
        self.svg_tag.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
        self.svg_tag.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
        self.svg_dom.appendChild(self.svg_tag)
        def_tag = self.svg_dom.createElement('defs')
        self.svg_tag.appendChild(def_tag)
        self.svg_def = def_tag

        # set of required macros
        self.required_defs = set()

        self.style = CascadingStyles()
        self.style.appendScope()
        self.style['fill'] = '#fff'
        self.style['stroke'] = '#000000'
        self.style['stroke-width'] = '1.000000px'

        self.svg_graphroot = self.svg_dom.createElement('g')

        graphic_tag = self.svg_dom.createElement('g')
        graphic_tag.setAttribute('style', str(self.style))
        self.svg_graphroot.appendChild(graphic_tag)
        self.svg_tag.appendChild(self.svg_graphroot)
        self.svg_current_layer = graphic_tag

    @property
    def svg(self):
        """Return the svg document"""
        return self.svg_dom.toprettyxml(encoding='utf-8')

    def mk_hex(self, s: str) -> str:
        # s is a string of a float
        return f'{int(min(float(s) * 256, 255)):02x}'

    def extract_colour(self, col):
        # only gets rgb values (ignores a)
        return ''.join([self.mk_hex(col['r']),
                        self.mk_hex(col['g']),
                        self.mk_hex(col['b'])])

    def set_graffle_font(self, font):
        if font is None:
            return
        fontstuffs = []
        font_col = '000000'

        if font.get('Color') is not None:
            grap_col = font.get('Color')
            try:
                font_col = self.extract_colour(grap_col)
            except:
                font_col = '000000'
        fontstuffs.append(f'fill:#{font_col}')
        fontstuffs.append(f'stroke:#{font_col}')
        fontstuffs.append('stroke-width:0.1px')

        fontfam = font.get('Font')
        if fontfam is not None:
            if fontfam == 'LucidaGrande':
                fontfam = 'Luxi Sans'
            elif fontfam == 'Courier':
                fontfam = 'Courier New'
            elif fontfam == 'GillSans':
                fontfam = 'Arial Narrow'
            fontstuffs.append(f'font-family: {fontfam}')

        size = font.get('Size')
        if size is not None:
            fontstuffs.append(f'font-size:{int(size)}px')

        self.svg_current_font = ';'.join(fontstuffs)

    def add_layer(self, graffle_interpreter, graphics_list):
        current_layer = self.svg_current_layer
        self.style.appendScope()
        g_emt = self.svg_dom.createElement('g')
        g_emt.setAttribute('style', str(self.style))
        current_layer.appendChild(g_emt)
        self.svg_current_layer = g_emt
        graffle_interpreter.iterate_graffle_graphics(graphics_list)
        self.style.popScope()
        self.svg_current_layer = current_layer

    def add_adjustable_arrow(self, bounds, graphic, **opts):
        x, y, width, height = [float(a) for a in bounds]
        ratio = float(graphic['ShapeData']['ratio'])
        neck = float(graphic['ShapeData']['width'])
        neck_delta = height * (1-ratio) / 2
        self.add_path([
                       [x, y+neck_delta],
                       [x+width-neck, y+neck_delta],
                       [x+width-neck, y],
                       [x+width, y+height/2],
                       [x+width-neck, y+height],
                       [x+width-neck, y+height-neck_delta],
                       [x, y+height-neck_delta],
                      ],
                      closepath=True,
                      **opts)

    def add_diamond(self, bounds, **opts):
        x, y, width, height = [float(a) for a in bounds]
        xmiddle = x+width/2
        ymiddle = y+height/2
        self.add_path([[x, ymiddle],
                       [xmiddle, y+height],
                       [x+width, ymiddle],
                       [xmiddle, y]],
                      closepath=True,
                      **opts)

    def add_path(self, pts, **opts):
        # do geometry mapping here
        mypts = pts
        if opts.get('HFlip', False):
            mypts = geom.h_flip_points(mypts)
        if opts.get('VFlip', False):
            mypts = geom.v_flip_points(mypts)
        if opts.get('Rotation') is not None:
            mypts = geom.rotate_points(mypts, opts['Rotation'])

        for (localx, localy) in mypts:
            self.__bb_point(localx, localy)

        ptStrings = [','.join([str(b) for b in a]) for a in mypts]
        line_string = f'M {ptStrings[0]}' + ' '.join(f' L {a}' for a in ptStrings[1:])
        if opts.get('closepath', False):
            line_string = line_string + ' z'
        path_tag = self.svg_dom.createElement('path')
        path_tag.setAttribute('id', opts.get('id', ''))
        path_tag.setAttribute('style', str(self.style.scopeStyle()))
        path_tag.setAttribute('d', line_string)
        self.svg_current_layer.appendChild(path_tag)

    def add_horizontal_triangle(self, bounds, **opts):
        """Graffle has the "HorizontalTriangle" Shape"""
        x, y, width, height = [float(a) for a in bounds]
        self.add_path([[x, y],
                       [x+width, y+height/2],
                       [x, y+height]],
                      closepath=True,
                      **opts)

    def add_image(self, bounds, **opts):
        """SVG viewers should support images - unfortunately many don't :-("""
        x, y, width, height = [float(a) for a in bounds]
        image_tag = self.svg_dom.createElement('image')
        image_tag.setAttribute('x', str(x))
        image_tag.setAttribute('y', str(y))
        image_tag.setAttribute('width', str(width))
        image_tag.setAttribute('height', str(height))
        image_tag.setAttribute('xlink:href', str(opts.get('href', '')))
        image_tag.setAttribute('style', str(self.style.scopeStyle()))
        self.__bb_box(x, y, width, height)
        self.svg_current_layer.appendChild(image_tag)

    def add_right_triangle(self,  bounds, **opts):
        """Graffle has the "RightTriangle" Shape"""
        x, y, width, height = [float(a) for a in bounds]
        self.add_path([[x, y],
                       [x+width, y+height],
                       [x, y+height]],
                      closepath=True,
                      **opts)

    def add_vertical_triangle(self, bounds, **opts):
        """Graffle has the "RightTriangle" Shape"""
        x, y, width, height = [float(a) for a in bounds]
        self.add_path([[x, y],
                       [x+width, y],
                       [x+width/2, y+height]],
                      closepath=True, **opts)

    def add_rect(self,  **opts):
        """Add an svg rect"""
        if opts is None:
            opts = {}
        rect_tag = self.svg_dom.createElement('rect')
        rect_tag.setAttribute('id', opts.get('id', ''))
        rect_tag.setAttribute('width', str(opts['width']))
        rect_tag.setAttribute('height', str(opts['height']))
        rect_tag.setAttribute('x', str(opts.get('x', '0')))
        rect_tag.setAttribute('y', str(opts.get('y', '0')))
        if opts.get('rx') is not None:
            rect_tag.setAttribute('rx', str(opts['rx']))
            rect_tag.setAttribute('ry', str(opts['ry']))
        rect_tag.setAttribute('style', str(self.style.scopeStyle()))
        self.svg_current_layer.appendChild(rect_tag)
        self.__bb_box(opts.get('x', '0'), opts.get('y', '0'),
                      opts['width'], opts['height'])

    def add_ellipse(self,  bounds, **opts):
        # Centre of circle.
        c = [bounds[i] + (bounds[i+2]/2.0) for i in [0, 1]]
        rx = bounds[2] / 2.0
        ry = bounds[3] / 2.0
        circle_tag = self.svg_dom.createElement('ellipse')
        circle_tag.setAttribute('id', opts.get('id', ''))
        circle_tag.setAttribute('style', str(self.style.scopeStyle()))
        circle_tag.setAttribute('cx', str(c[0]))
        circle_tag.setAttribute('cy', str(c[1]))
        circle_tag.setAttribute('rx', str(rx))
        circle_tag.setAttribute('ry', str(ry))
        self.svg_current_layer.appendChild(circle_tag)
        self.__bb_box(c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry)

    def add_cloud(self, bounds, **opts):
        """Add a cloud element"""
        self.required_defs.add('network_cloud')
        x, y, dx, dy = bounds
        cloud_tag = self.svg_dom.createElement('g')
        cloud_tag.setAttribute('id', opts.get('id', ''))
        cloud_tag.setAttribute('style', str(self.style.scopeStyle()))
        cloud_tag.setAttribute('transform',
                f'translate({x},{y}) scale({float(dx)/500.0},{float(dy)/500.0})')
        p = xml.dom.minidom.parseString("<use xmlns:xlink='http://www.w3.org/1999/xlink' xlink:href='#network_cloud' />")
        def_node = p.childNodes[0]
        cloud_tag.appendChild(def_node)
        self.svg_current_layer.appendChild(cloud_tag)
        self.__bb_box(x, y, dx, dy)

    def add_text(self,**opts):
        """Add an svg text element"""
        text_tag = self.svg_dom.createElement('text')
        text_tag.setAttribute('id',str(opts.get('id',''))+'_text')
        text_tag.setAttribute('x',str(opts.get('x','0')))
        text_tag.setAttribute('y',str(opts.get('y','0')))
        # text_tag.setAttribute('dominant-baseline','mathematical')
        text_tag.setAttribute('style', self.svg_current_font)
        self.svg_current_layer.appendChild(text_tag)

        # Generator
        lines = extractRTFString(opts['rtftext'])
        font_info =  opts.get('fontinfo',None)
        if font_info is not None:
            font_height = int(font_info.get('Size'))
        else:
            font_height = 12
        total_height = 0.0
        for span in lines:
            total_height += float(span['style'].get('font-size', f'{font_height:.1f}px')[:-2])
        y_diff = float(opts.get('y', '12.0')) + opts.get('height', 0)/2 - total_height/2
        line_id = opts['id']
        linenb = 0
        for span in lines:
            y_diff += float(span['style'].get('font-size', f'{font_height:.1f}px')[:-2])
            linenb += 1
            opts['id'] = f'{line_id}_line{linenb}'
            self.add_line(text_tag, text=span['string'], style=span['style'],
                         y_pos=y_diff, line_height=font_height, **opts)
        self.__bb_box(opts.get('x', '0'),
                      opts.get('y', '0'),
                      opts.get('width', '0'),
                      opts.get('height', '0'))

    def add_line(self, textnode, **opts):
        """Add a line of text"""
        tspan_node = self.svg_dom.createElement('tspan')
        tspan_node.setAttribute('id', opts.get('id', ''))
        align = opts.get('style', {'text-align': 'left'}).get('text-align', 'left')
        x = opts.get('x', 0)
        if align == 'center':
            tspan_node.setAttribute('text-anchor', 'middle')
            x += opts.get('width', 0)/2
        elif align == 'right':
            x += opts.get('width', 0)
        tspan_node.setAttribute('x', str(x))
        y_pos = float(opts.get('y_pos', 0))
        tspan_node.setAttribute('y', str(y_pos))
        if (opts.get('style') is not None) and len(opts.get('style')) > 0:
            thestyle = opts.get('style')
            for k, v in thestyle.items():
                tspan_node.setAttribute(k, v)
        actual_string = self.svg_dom.createTextNode(opts.get('text', ' '))
        tspan_node.appendChild(actual_string)
        textnode.appendChild(tspan_node)

    def add_document_bounds(self):
        if self.svg_bounds:
            (minx, miny, maxx, maxy) = self.svg_bounds
            # self.svg_tag.setAttribute('width', str(maxx - minx))
            # self.svg_tag.setAttribute('height', str(maxy - miny))
            self.svg_graphroot.setAttribute('transform',
                                            f'translate({-minx},{-miny})')

    def add_requirements(self):
        for required in self.required_defs:
            if required.startswith('Arrow1Lend'):
                shape,  color, width = required.split('_')
                scale = 1.0 / ((float(width[0:-2])-1.0)/20.0+1.0)
                p = xml.dom.minidom.parseString("""
                <defs><marker
                   orient='auto'
                   refY='0.0'
                   refX='0.0'
                   id='{required}'
                   style='overflow:visible;'>
                  <path
                     id='path_{required}'
                     d='M -5,0.0 L -5,-2.0 L 0.0,0.0 L -5,2.0 z '
                     style='fill:#{color};fill-rule:evenodd;stroke:#{color};stroke-width:1.0px;marker-start:none;'
                     transform='scale({scale})' />
                </marker></defs>""")
                def_node = p.childNodes[0]
                for node in def_node.childNodes:
                    self.svg_def.appendChild(node)
            if required.startswith('Arrow1Lstart'):
                shape,  color, width = required.split('_')
                scale = 1.0 / ((float(width[0:-2])-1.0)/20.0+1.0)
                p = xml.dom.minidom.parseString(f"""
                <defs><marker
                   orient='auto'
                   refY='0.0'
                   refX='0.0'
                   id='{required}'
                   style='overflow:visible'>
                  <path
                     id='path_{required}'
                     d='M 5,0.0 L 5.0,-2.0 L 0.0,0.0 L 5.0,2.0 z'
                     style='fill:#{color};fill-rule:evenodd;stroke:#{color};stroke-width:1.0px;marker-start:none'
                     transform='scale({scale})'/>
                </marker></defs>""")
                def_node = p.childNodes[0]
                for node in def_node.childNodes:
                    self.svg_def.appendChild(node)

        if 'Arrow2Lend' in self.required_defs:
            # TODO
            p = xml.dom.minidom.parseString("""
            <defs><marker
               orient='auto'
               refY='0.0'
               refX='0.0'
               id='Arrow2Lend'
               overflow='visible'
               stroke='currentColor'>
              <path
                 id='Arrow2Lend'
                 d='M 10.0,-2.0 L 0.0,0.0 L 10.0,2.0'
                 style='fill:none;stroke:#000000;stroke-width:1.0px;marker-start:none' />
            </marker></defs>""")
            def_node = p.childNodes[0]
            for node in def_node.childNodes:
                self.svg_def.appendChild(node)

        if 'Arrow2Lstart' in self.required_defs:
            p = xml.dom.minidom.parseString("""
            <defs><marker
               orient='auto'
               refY='0.0'
               refX='0.0'
               id='Arrow2Lstart'
               overflow='visible'
               stroke='currentColor'>
              <path
                 id='pathStickArrow'
                 d='M -10.0,-2.0 L 0.0,0.0 L -10.0,2.0'
                 style='fill:none;stroke:#000000;stroke-width:1.0px;marker-start:none'/>
            </marker></defs>""")
            def_node = p.childNodes[0]
            for node in def_node.childNodes:
                self.svg_def.appendChild(node)

        if 'DropShadow' in self.required_defs:
            p = xml.dom.minidom.parseString("""
            <defs><filter id='DropShadow' filterRes='100' x='0' y='0'>
               <feGaussianBlur stdDeviation='3' result='MyBlur'/>
               <feOffset in='MyBlur' dx='2' dy='4' result='movedBlur'/>
               <feMerge>
                   <feMergeNode in='movedBlur'/>
                   <feMergeNode in='SourceGraphic'/>
               </feMerge>
            </filter></defs>""")
            def_node = p.childNodes[0]
            for node in def_node.childNodes:
                self.svg_def.appendChild(node)

        if 'CrowBall' in self.required_defs:
            p = xml.dom.minidom.parseString("""
            <defs><marker
            refX='0'
            refY='0'
            orient='auto'
            id='mCrowBall'
            style='overflow:visible'>
            <path d='M 0.0,2.5 L 7.5,0.0 L 0.0,-2.5'
             style='stroke:#000;stroke-width:1.0px;marker-start:none;fill:none;' />
            <circle cx='10' cy='0' r='2.5' style='stroke-width:1px; stroke: #000; fill:none;'/>
            </marker></defs>""")
            def_node = p.childNodes[0]
            for node in def_node.childNodes:
                self.svg_def.appendChild(node)

        if 'Bar' in self.required_defs:
            p = xml.dom.minidom.parseString("""
            <defs><marker
            refX='0'
            refY='0'
            orient='auto'
            id='mBar'
            style='overflow:visible'>
            <path d='M -7.5,-2.5 L -7.5,2.5'
             style='stroke:#000;stroke-width:1.0px;marker-start:none;fill:none;' />
            </marker></defs>""")
            def_node = p.childNodes[0]
            for node in def_node.childNodes:
                self.svg_def.appendChild(node)

        if 'network_cloud' in self.required_defs:
            ''' cloud shape 500x500 '''
            p = xml.dom.minidom.parseString("""
            <defs><g id='network_cloud'>
            <path d='M 127.5 106.25 C 127.5 106.25 126.25 18.7501 231.25 45 C 336.25 71.25 317.5 115 318.75 115 C 320 115 300 61.25 380 51.25 C 452.5 57.5 486.25 71.25 482.5 117.5 C 478.75 163.75 443.75 175 443.75 175 C 443.75 175 507.5 181.25 490 275 C 462.5 340 462.5 333.75 398.75 341.25 C 370 330 368.75 320 368.75 320 C 368.75 320 421.25 368.75 342.5 400 C 253.75 423.75 242.5 402.5 205 391.25 C 168.75 368.75 176.25 341.25 176.25 341.25 C 176.25 341.25 198.75 387.5 122.5 396.25 C 46.25 405 17.5 387.5 3.75 316.25 C 2.08616e-06 262.5 67.5 257.5 67.5 257.5 C 67.5 257.5 26.25 258.75 15 231.25 C 3.75 203.75 -3.75 167.5 30 118.75 C 92.5 60 135 98.75 127.5 106.25 z '/>
            </g></defs>""")
            def_node = p.childNodes[0]
            for node in def_node.childNodes:
                self.svg_def.appendChild(node)

    def set_graffle_style(self, style):
        if style.get('fill') is not None:
            fill = style.get('fill')
            if fill.get('Draws', '') == 'NO':
                # don't display
                self.style['fill'] = 'none'
            else:
                grap_col = fill.get('Color')
                if grap_col is not None:
                    fill_col = self.extract_colour(grap_col)
                    self.style['fill'] = f'#{fill_col}'

        if style.get('stroke') is not None:
            stroke = style.get('stroke')
            if stroke.get('Draws', '') == 'NO':
                self.style['stroke'] = 'none'
            else:
                grap_col = stroke.get('Color', {'r': 0.0, 'g': 0.0, 'b': 0.0})
                if grap_col is not None:
                    stroke_col = self.extract_colour(grap_col)
                    self.style['stroke'] = f'#{stroke_col}'

            if stroke.get('Width') is not None:
                width = stroke['Width']
                self.style['stroke-width'] = f'{float(width)}px'

            if stroke.get('HeadArrow') is not None:
                headarrow = stroke['HeadArrow']
                marker_end = 'none'
                headscale = stroke.get('HeadScale', 1.0)
                if headarrow == 'FilledArrow':
                    marker_end = 'Arrow1Lend_{style}_{width}px'.format(
                        style=self.style["stroke"][1:],
                        width=float(self.style["stroke-width"][:-2])*headscale)
                    self.style['marker-end'] = f'url(#{marker_end})'
                    self.required_defs.add(marker_end)
                elif headarrow == 'StickArrow':
                    self.style['marker-end'] = 'url(#Arrow2Lend)'
                    self.required_defs.add('Arrow2Lend')
                elif headarrow == 'Bar':
                    # TODO
                    self.style['marker-end'] = 'url(#mBar)'
                    self.required_defs.add('Bar')
                elif headarrow == '0':
                    self.style['marker-end'] = 'none'
                else:
                    print(f'unknown HeadArrow {headarrow}')
                    self.style['marker-end'] = 'url(#Arrow2Lend)'
                    self.required_defs.add('Arrow2Lend')

            if stroke.get('TailArrow') is not None:
                tailarrow = stroke['TailArrow']
                tailscale = stroke.get('TailScale', 1.0)
                if tailarrow == 'FilledArrow':
                    marker_start = 'Arrow1Lstart_{style}_{width}px'.format(
                        style=self.style["stroke"][1:],
                        width=float(self.style["stroke-width"][:-2])*tailscale)
                    self.style['marker-start'] = 'url(#{marker_start})'
                    self.required_defs.add(marker_start)
                elif tailarrow == 'StickArrow':
                    self.style['marker-end'] = 'url(#Arrow2Lstart)'
                    self.required_defs.add('Arrow2Lstart')
                elif tailarrow == 'CrowBall':
                    self.style['marker-start'] = 'url(#mCrowBall)'
                    self.required_defs.add('CrowBall')

                elif tailarrow == '0':
                    self.style['marker-start'] = 'none'
                else:
                    print(f'unknown TailArrow {headarrow}')
                    self.style['marker-end'] = 'url(#Arrow2Lstart)'
                    self.required_defs.add('Arrow2Lstart')

            if stroke.get('Pattern') is not None:
                pattern = stroke['Pattern']
                if pattern == 1:
                    self.style['stroke-dasharray'] = '3 3'
                elif pattern == 2:
                    self.style['stroke-dasharray'] = '5 5'
                else:
                    print(f'unknown pattern {pattern}')
                    self.style['stroke-dasharray'] = '1 1'

        if style.get('shadow', {}).get('Draws', 'NO') != 'NO':
            # for some reason graffle has a shadow by default
            self.required_defs.add('DropShadow')
            self.style['filter'] = 'url(#DropShadow)'


if __name__ == '__main__':
    gi = GraffleInterpreter()
    svgTarget = TargetSvg()
    gi.set_target(svgTarget)
    gi.dict = GraffleParser().walk_graffle_file('progit.graffle')
    for source_index in range(82):
        gi.extract_page(page=source_index)
        f = open(f'figure{source_index}.svg', 'w')
        f.write(gi.target.svg)
        f.close()
