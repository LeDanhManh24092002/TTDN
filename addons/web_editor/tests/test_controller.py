# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import binascii

from io import BytesIO
from PIL import Image

from odoo.addons.http_routing.models.ir_http import slug
import odoo.tests
from odoo.tools.misc import file_open
from odoo.tests.common import HttpCase

@odoo.tests.tagged('-at_install', 'post_install')
class TestController(HttpCase):
    def test_01_illustration_shape(self):
        self.authenticate('admin', 'admin')
        # SVG with all replaceable colors.
        svg = b"""
<svg viewBox="0 0 400 400">
  <rect width="300" height="300" style="fill:#3AADAA;" />
  <rect x="20" y="20" width="300" height="300" style="fill:#7C6576;" />
  <rect x="40" y="40" width="300" height="300" style="fill:#F6F6F6;" />
  <rect x="60" y="60" width="300" height="300" style="fill:#FFFFFF;" />
  <rect x="80" y="80" width="300" height="300" style="fill:#383E45;" />
</svg>
        """
        # Need to bypass security check to write image with mimetype image/svg+xml
        context = {'binary_field_real_user': self.env['res.users'].sudo().browse([1])}
        attachment = self.env['ir.attachment'].sudo().with_context(context).create({
            'name': 'test.svg',
            'mimetype': 'image/svg+xml',
            'datas': binascii.b2a_base64(svg, newline=False),
            'public': True,
            'res_model': 'ir.ui.view',
            'res_id': 0,
        })
        # Shape illustration with slug.
        url = '/web_editor/shape/illustration/%s' % slug(attachment)
        palette = 'c1=%233AADAA&c2=%237C6576&&c3=%23F6F6F6&&c4=%23FFFFFF&&c5=%23383E45'
        attachment['url'] = '%s?%s' % (url, palette)

        response = self.url_open(url)
        self.assertEqual(200, response.status_code, 'Expect response')
        self.assertEqual(svg, response.content, 'Expect unchanged SVG')

        response = self.url_open(url + '?c1=%23ABCDEF')
        self.assertEqual(200, response.status_code, 'Expect response')
        self.assertEqual(len(svg), len(response.content), 'Expect same length as original')
        self.assertTrue('ABCDEF' in str(response.content), 'Expect patched c1')
        self.assertTrue('3AADAA' not in str(response.content), 'Old c1 should not be there anymore')

        # Shape illustration without slug.
        url = '/web_editor/shape/illustration/noslug'
        attachment['url'] = url

        response = self.url_open(url)
        self.assertEqual(200, response.status_code, 'Expect response')
        self.assertEqual(svg, response.content, 'Expect unchanged SVG')

        response = self.url_open(url + '?c1=%23ABCDEF')
        self.assertEqual(200, response.status_code, 'Expect response')
        self.assertEqual(len(svg), len(response.content), 'Expect same length as original')
        self.assertTrue('ABCDEF' in str(response.content), 'Expect patched c1')
        self.assertTrue('3AADAA' not in str(response.content), 'Old c1 should not be there anymore')

    def test_font_to_img(self):
        # This test was introduced because the play button was cropped in noble following some adaptation.
        # This test is able to reproduce the issue and ensure that the expected result is the right one
        # comparing image is not ideal, but this should work in most case, maybe adapted if the font is changed.

        response = self.url_open('/web_editor/font_to_img/61802/rgb(0,143,140)/rgb(255,255,255)/190x200')

        img = Image.open(BytesIO(response.content))
        self.assertEqual(img.size, (201, 200), 'Looks strange regarding request but this is the current result')
        # Image is a play button
        img_reference = Image.open(file_open('web_editor/tests/play.png', 'rb'))
        self.assertEqual(img, img_reference, "Result image should be the play button")
