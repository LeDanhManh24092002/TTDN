from odoo import models, fields, api

class LoaiVanBan(models.Model):
    _name = 'loai_van_ban'
    _description = 'Bảng chứa danh sách văn bản gửi đến '

    van_ban_den_id = fields.Many2one("van_ban_den", string="Văn bản đến ")
    loai = fields.Selection(
        [
            ("Hỏa tốc ", "Hỏa tốc "),
            ("Thượng khẩn ", "Thượng khẩn "),
            ("Khuẩn ", "Khuẩn ")
        ],
        string="Loại ", default="Hỏa tốc "
    )
   
    
    
    
    