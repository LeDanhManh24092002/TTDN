from odoo import models, fields

class DonVi(models.Model):
    _name = 'don_vi'
    _description = 'Đơn vị'

    ma_don_vi = fields.Char(string="Mã đơn vị", required=True)
    ten_don_vi = fields.Char(string="Tên đơn vị", required=True)

