#!/usr/bin/env python3

import xml.dom.minidom
from unittest import makeSuite, TestCase, TestSuite
from unittest.mock import Mock,  patch

from main import TargetSvg,  GraffleParser,  GraffleInterpreter


class TestMkHex(TestCase):
    def setUp(self):
        self.gi = TargetSvg()

    def testZero(self):
        self.assertEqual(self.gi.mk_hex(0.0), '00')

    def testFull(self):
        self.assertEqual(self.gi.mk_hex(1.0), 'ff')

    def testOne(self):
        self.assertEqual(self.gi.mk_hex(1.0/255), '01')

    def testFifteen(self):
        self.assertEqual(self.gi.mk_hex(15.0/255), '0f')

    def test254(self):
        self.assertEqual(self.gi.mk_hex(254.0/255), 'fe')


class TestGraffleParser(TestCase):
    def setUp(self):
        self.gp = GraffleParser()

    def tearDown(self):
        del self.gp

    def testGraffleDictInteger(self):
        p = xml.dom.minidom.parseString('<dict><key>ImageCounter</key><integer>1</integer></dict>')
        dict = self.gp.return_graffle_dict(p.firstChild)
        self.assertEqual(dict['ImageCounter'], '1')

    def testGraffleDictReal(self):
        p = xml.dom.minidom.parseString('<dict><key>Size</key><real>19</real></dict>')
        dict = self.gp.return_graffle_dict(p.firstChild)
        self.assertEqual(dict['Size'], '19')

    def testGraffleDictString(self):
        p = xml.dom.minidom.parseString('<dict><key>Shape</key><string>RoundRect</string></dict>')
        dict = self.gp.return_graffle_dict(p.firstChild)
        self.assertEqual(dict['Shape'], 'RoundRect')


class Scope(dict):
    def __init__(self):
        self.appendScope = Mock()
        self.popScope = Mock()
        dict.__init__(self)


class TestGraffleInterpreterBoundingBox(TestCase):
    def setUp(self):
        self.gi = GraffleInterpreter()
        self.MockTarget = Mock()
        self.MockTarget.style = Scope()
        self.gi.set_target(self.MockTarget)

    def tearDown(self):
        del self.MockTarget
        del self.gi

    @patch('geom.out_of_boundingbox')
    def testTextWithCoordinatesOutOfBoundinBoxShouldNotAddToTarget(self, mockBounds):
        self.gi.bounding_box = ((-1, -1),  (1,  1))
        mockBounds.return_value = True
        self.gi.iterate_graffle_graphics([{
            'Class': 'ShapedGraphic',
            'Bounds': '{{0, 0}, {756, 553}}',
            'Shape': 'RoundRect',
            'ID': 5,
            'Text': {'Text': 'test'}}])
        self.assertFalse(any([mthd_call[0] == 'add_text' for mthd_call in self.MockTarget.method_calls]))

    @patch('geom.out_of_boundingbox')
    def testShapedGraphicWithCoordinatesOutOfBoundinBoxShouldNotAddToTarget(self, mockBounds):
        self.gi.bounding_box = ((-1, -1),  (1,  1))
        mockBounds.return_value = True
        self.gi.iterate_graffle_graphics([{
            'Class': 'ShapedGraphic',
            'Bounds': '{{0, 0}, {756, 553}}',
            'Shape': 'RoundRect',
            'ID': 5}])
        self.assertFalse(any([mthd_call[0] == 'add_rect' for mthd_call in self.MockTarget.method_calls]))

    @patch('geom.out_of_boundingbox')
    def testShapedGraphicWithCoordinatesInBoundingBoxShouldAddToTarget(self, mockBounds):
        self.gi.bounding_box = ((-1, -1),  (1,  1))
        mockBounds.return_value = False
        self.gi.iterate_graffle_graphics([{
            'Class': 'ShapedGraphic',
            'Bounds': '{{0, 0}, {756, 553}}',
            'Shape': 'RoundRect',
            'ID': 5}])
        self.assertTrue(any([mthd_call[0] == 'add_rect' for mthd_call in self.MockTarget.method_calls]))

    def testShapedGraphicWithNoBoundingBoxShouldAddToTarget(self):
        self.gi.bounding_box = None
        self.gi.iterate_graffle_graphics([{
            'Class': 'ShapedGraphic',
            'Bounds': '{{0, 0}, {756, 553}}',
            'Shape': 'RoundRect',
            'ID': 5}])
        self.assertTrue(any([mthd_call[0] == 'add_rect' for mthd_call in self.MockTarget.method_calls]))

    @patch('geom.out_of_boundingbox')
    def testLineGraphicWithCoordinatesOutOfBoundinBoxShouldNotAddToTarget(self, mockBounds):
        self.gi.bounding_box = ((-1, -1),  (1,  1))
        mockBounds.return_value = True
        self.gi.iterate_graffle_graphics([{
            'Class': 'LineGraphic',
            'Points': ['{0, 0}', '{756, 553}'],
            'ID': 5}])
        self.assertFalse(any([mthd_call[0] == 'add_path' for mthd_call in self.MockTarget.method_calls]))

    @patch('geom.out_of_boundingbox')
    def testLineGraphicWithCoordinatesInBoundingBoxShouldAddToTarget(self, mockBounds):
        self.gi.bounding_box = ((-1, -1),  (1,  1))
        mockBounds.return_value = False
        self.gi.iterate_graffle_graphics([{
            'Class': 'LineGraphic',
            'Points': ['{0, 0}', '{756, 553}'],
            'ID': 5}])
        self.assertTrue(any([mthd_call[0] == 'add_path' for mthd_call in self.MockTarget.method_calls]))

    def testLineGraphicWithNoBoundingBoxShouldAddToTarget(self):
        self.gi.iterate_graffle_graphics([{
            'Class': 'LineGraphic',
            'Points': ['{0, 0}', '{756, 553}'],
            'ID': 5}])
        self.assertTrue(any([mthd_call[0] == 'add_path' for mthd_call in self.MockTarget.method_calls]))


class TestTargetSvg(TestCase):
    def setUp(self):
        self.ts = TargetSvg()

    def tearDown(self):
        del self.ts

    def testReset(self):
        self.ts.reset()
        self.assertFalse(self.ts.style is None)
        self.assertFalse(self.ts.svg_def is None)
        self.assertFalse(self.ts.svg_dom is None)
        self.assertFalse(self.ts.svg_current_layer is None)
        self.assertFalse(self.ts.required_defs is None)

    def testArrowHeadColor(self):
        self.ts.set_graffle_style({
            'stroke': {'Color': {'r': 0.5, 'g': 0.5, 'b': 0.5},
                       'HeadArrow': 'FilledArrow'}})
        self.assertEqual(self.ts.style['marker-end'], 'url(#Arrow1Lend_808080_1.000000px)')
        self.assertTrue('Arrow1Lend_808080_1.000000px' in self.ts.required_defs)

    def testArrowTailColor(self):
        self.ts.set_graffle_style({'stroke': {'Color': {'r': 0.5, 'g': 0.5, 'b': 0.5},
                                              'TailArrow': 'FilledArrow'}})
        self.assertEqual(self.ts.style['marker-start'],
                'url(#Arrow1Lstart_808080_1.000000px)')
        self.assertTrue('Arrow1Lstart_808080_1.000000px' in self.ts.required_defs)


def get_tests():
    TS = TestSuite()
    TS.addTest(makeSuite(TestMkHex))
    TS.addTest(makeSuite(TestGraffleParser))
    TS.addTest(makeSuite(TestGraffleInterpreterBoundingBox))
    TS.addTest(makeSuite(TestTargetSvg))
    return TS
