# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountAccountTag(models.Model):
    _name = 'account.account.tag'
    _description = 'Account Tag'

    name = fields.Char('Tag Name', required=True)
    applicability = fields.Selection([('accounts', 'Accounts'), ('taxes', 'Taxes'), ('products', 'Products')], required=True, default='accounts')
    color = fields.Integer('Color Index')
    active = fields.Boolean(default=True, help="Set active to false to hide the Account Tag without removing it.")
    tax_report_line_ids = fields.Many2many(string="Tax Report Lines", comodel_name='account.tax.report.line', relation='account_tax_report_line_tags_rel', help="The tax report lines using this tag")
    tax_negate = fields.Boolean(string="Negate Tax Balance", help="Check this box to negate the absolute value of the balance of the lines associated with this tag in tax report computation.")
    country_id = fields.Many2one(string="Country", comodel_name='res.country', help="Country for which this tag is available, when applied on taxes.")

    @api.model
    def _get_tax_tags(self, tag_name, country_id):
        """ Returns all the tax tags corresponding to the tag name given in parameter
        in the specified country.
        """
        escaped_tag_name = tag_name.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')
        domain = [('name', '=like', '_' + escaped_tag_name), ('country_id', '=', country_id), ('applicability', '=', 'taxes')]
        return self.env['account.account.tag'].with_context(active_test=False).search(domain)

    def name_get(self):
        if not self.env.company.multi_vat_foreign_country_ids:
            return super().name_get()

        res = []
        for tag in self:
            name = tag.name
            if tag.applicability == "taxes" and tag.country_id and tag.country_id != self.env.company.account_fiscal_country_id:
                name = _("%s (%s)", tag.name, tag.country_id.code)
            res.append((tag.id, name,))

        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_master_tags(self):
        master_xmlids = [
            "account_tag_operating",
            "account_tag_financing",
            "account_tag_investing",
        ]
        for master_xmlid in master_xmlids:
            master_tag = self.env.ref(f"account.{master_xmlid}", raise_if_not_found=False)
            if master_tag and master_tag in self:
                raise UserError(_("You cannot delete this account tag (%s), it is used on the chart of account definition.", master_tag.name))
