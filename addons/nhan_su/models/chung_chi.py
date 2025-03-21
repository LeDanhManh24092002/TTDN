from odoo import models, fields, api


class ChungChi(models.Model):
    _name = 'chung_chi'
    _description = 'Chứng chỉ của nhân viên '
    _rec_name= 'ten_chung_chi'

    ten_chung_chi = fields.Char("Tên chứng chỉ", required=True)
    loai = fields.Char("Loại ", required=True)
    noi_cap = fields.Char("Nơi cấp ", required=True)
