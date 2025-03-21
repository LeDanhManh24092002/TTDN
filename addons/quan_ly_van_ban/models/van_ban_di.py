from odoo import models, fields, api
from datetime import date


class VanBanDi(models.Model):
    _name = 'van_ban_di'
    _description = 'Văn bản đến rồi lại đi kkk'
    _rec_name = 'ten_van_ban'

    so_hieu_van_ban = fields.Char("Số hiệu văn bản ", required=True)
    ten_van_ban = fields.Char("Tên văn bản ", required=True)
    so_van_ban_di = fields.Char("Số văn bản đi ")
    thoi_gian_gui = fields.Date("Thời gian văn bản gửi đi ", required=True)
    noi_den = fields.Char("Nơi đến ", required = True)
    
    
    
