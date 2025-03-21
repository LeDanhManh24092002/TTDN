from odoo import models, fields, api


class BangCap(models.Model):
    _name = 'bang_cap'
    _description = 'Bằng cấp nhân viên '
    _rec_name= 'ten_bang_cap'

    ten_bang_cap = fields.Char("Tên bằng cấp", required=True)
    loai = fields.Char("Loại ", required=True)
    noi_cap = fields.Char("Nơi cấp ", required=True)
