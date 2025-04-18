# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from lxml import objectify
from werkzeug import urls

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tools.misc import hmac as hmac_tool

_logger = logging.getLogger(__name__)


class PaymentTestUtils(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        cls.base_url = cls.env['ir.config_parameter'].get_param('web.base.url')

    def _generate_test_access_token(self, *values):
        """ Generate an access token based on the provided values for testing purposes.

        This methods returns a token identical to that generated by
        payment.utils.generate_access_token but uses the test class environment rather than the
        environment of odoo.http.request.

        See payment.utils.generate_access_token for additional details.

        :param list values: The values to use for the generation of the token
        :return: The generated access token
        :rtype: str
        """
        token_str = '|'.join(str(val) for val in values)
        access_token = hmac_tool(self.env(su=True), 'generate_access_token', token_str)
        return access_token

    def _build_url(self, route):
        return urls.url_join(self.base_url, route)

    def _extract_values_from_html_form(self, html_form):
        """ Extract the transaction rendering values from an HTML form.

        :param str html_form: The HTML form
        :return: The extracted information (action & inputs)
        :rtype: dict[str:str]
        """
        html_tree = objectify.fromstring(html_form)
        action = html_tree.get('action')
        inputs = {form_input.get('name'): form_input.get('value') for form_input in html_tree.input}
        return {
            'action': action,
            'inputs': inputs,
        }
