# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ContractType(models.Model):
    _name = 'hr.contract.type'
    _description = 'Contract Type'

    name = fields.Char(required=True)

class HrPayrollStructureType(models.Model):
    _name = 'hr.payroll.structure.type'
    _description = 'Salary Structure Type'

    name = fields.Char('Salary Structure Type')
    default_resource_calendar_id = fields.Many2one(
        'resource.calendar', 'Default Working Hours',
        default=lambda self: self.env.company.resource_calendar_id)
    country_id = fields.Many2one('res.country', string='Country', default=lambda self: self.env.company.country_id)
