# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.osv.expression import OR


class ResCompany(models.Model):
    _inherit = 'res.company'

    hr_attendance_overtime = fields.Boolean(string="Count Extra Hours")
    overtime_start_date = fields.Date(string="Extra Hours Starting Date")
    overtime_company_threshold = fields.Integer(string="Tolerance Time In Favor Of Company", default=0)
    overtime_employee_threshold = fields.Integer(string="Tolerance Time In Favor Of Employee", default=0)

    def write(self, vals):
        search_domain = False  # Overtime to generate
        delete_domain = False  # Overtime to delete

        overtime_enabled_companies = self.filtered('hr_attendance_overtime')
        # Prevent any further logic if we are disabling the feature
        is_disabling_overtime = False
        # If we disable overtime
        if 'hr_attendance_overtime' in vals and not vals['hr_attendance_overtime'] and overtime_enabled_companies:
            delete_domain = [('company_id', 'in', overtime_enabled_companies.ids)]
            vals['overtime_start_date'] = False
            is_disabling_overtime = True

        start_date = vals.get('hr_attendance_overtime') and vals.get('overtime_start_date')
        # Also recompute if the threshold have changed
        if not is_disabling_overtime and (
            start_date or 'overtime_company_threshold' in vals or 'overtime_employee_threshold' in vals):
            for company in self:
                # If we modify the thresholds only
                if start_date == company.overtime_start_date and \
                    (vals.get('overtime_company_threshold') != company.overtime_company_threshold) or\
                    (vals.get('overtime_employee_threshold') != company.overtime_employee_threshold):
                    search_domain = OR([search_domain, [('employee_id.company_id', '=', company.id)]])
                # If we enabled the overtime with a start date
                elif not company.overtime_start_date and start_date:
                    search_domain = OR([search_domain, [
                        ('employee_id.company_id', '=', company.id),
                        ('check_in', '>=', start_date)]])
                # If we move the start date into the past
                elif start_date and company.overtime_start_date > start_date:
                    search_domain = OR([search_domain, [
                        ('employee_id.company_id', '=', company.id),
                        ('check_in', '>=', start_date),
                        ('check_in', '<=', company.overtime_start_date)]])
                # If we move the start date into the future
                elif start_date and company.overtime_start_date < start_date:
                    delete_domain = OR([delete_domain, [
                        ('company_id', '=', company.id),
                        ('date', '<', start_date)]])

        res = super().write(vals)
        if delete_domain:
            self.env['hr.attendance.overtime'].search(delete_domain).unlink()
        if search_domain:
            self.env['hr.attendance'].search(search_domain)._update_overtime()

        return res
