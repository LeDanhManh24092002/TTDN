# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ReportProjectTaskUser(models.Model):
    _inherit = "report.project.task.user"

    sale_order_id = fields.Many2one('sale.order', string='Sales Order', readonly=True)

    def _select(self):
        return super()._select() + ", t.sale_order_id"

    def _group_by(self):
        return super()._group_by() + ", t.sale_order_id"
