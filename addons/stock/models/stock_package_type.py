# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, _


class PackageType(models.Model):
    _name = 'stock.package.type'
    _description = "Stock package type"
    _order = "sequence"

    def _get_default_length_uom(self):
        return self.env['product.template']._get_length_uom_name_from_ir_config_parameter()

    def _get_default_weight_uom(self):
        return self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()

    name = fields.Char('Package Type', required=True)
    sequence = fields.Integer('Sequence', default=1, help="The first in the sequence is the default one.")
    height = fields.Integer('Height', help="Packaging Height")
    width = fields.Integer('Width', help="Packaging Width")
    packaging_length = fields.Integer('Length', help="Packaging Length")
    max_weight = fields.Float('Max Weight', help='Maximum weight shippable in this packaging')
    barcode = fields.Char('Barcode', copy=False)
    weight_uom_name = fields.Char(string='Weight unit of measure label', compute='_compute_weight_uom_name', default=_get_default_weight_uom)
    length_uom_name = fields.Char(string='Length unit of measure label', compute='_compute_length_uom_name', default=_get_default_length_uom)
    company_id = fields.Many2one('res.company', 'Company', index=True)
    storage_category_capacity_ids = fields.One2many('stock.storage.category.capacity', 'package_type_id', 'Storage Category Capacity', copy=True)

    _sql_constraints = [
        ('barcode_uniq', 'unique(barcode)', "A barcode can only be assigned to one package type !"),
        ('positive_height', 'CHECK(height>=0)', 'Height must be positive'),
        ('positive_width', 'CHECK(width>=0)', 'Width must be positive'),
        ('positive_length', 'CHECK(packaging_length>=0)', 'Length must be positive'),
        ('positive_max_weight', 'CHECK(max_weight>=0.0)', 'Max Weight must be positive'),
    ]

    def _compute_length_uom_name(self):
        # FIXME This variable does not impact any logic, it is only used for the packaging display on the form view.
        #  However, it generates some confusion for the users since this UoM will be ignored when sending the requests
        #  to the carrier server: the dimensions will be expressed with another UoM and there won't be any conversion.
        #  For instance, with Fedex, the UoM used with the package dimensions will depend on the UoM of
        #  `fedex_weight_unit`. With UPS, we will use the UoM defined on `ups_package_dimension_unit`
        #  This is also confusing when length UoM of the database is `ft`. The dimensions are integers (not floats) and
        #  the UoM is not small enough (for instance, the user will not be able to define a package with a length
        #  of 10 in)
        self.length_uom_name = ""

    def _compute_weight_uom_name(self):
        for package_type in self:
            package_type.weight_uom_name = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()

    def copy(self, default=None):
        default = dict(default or {})
        default.update(name=_("%s (copy)") % self.name)
        return super().copy(default)
