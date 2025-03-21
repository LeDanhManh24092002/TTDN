from odoo import models, fields, api
from datetime import date

class DanhSachVanBanDen(models.Model):
    _name = 'danh_sach_van_ban_den'
    _description = 'Bảng chứa danh sách văn bản gửi đến '

    van_ban_den_id = fields.Many2one("van_ban_den", string="Văn Bản Đến")
    ma_van_ban_den = fields.Char(related="van_ban_den_id.ma_van_ban_den", string="Mã văn bản ", store=True)
    ngay_nhan = fields.Date(related="van_ban_den_id.ngay_nhan", string="Ngày nhận", store=True)
    nguoi_nhan = fields.Char(related="van_ban_den_id.nguoi_nhan", string="Người nhận", store=True)
    noi_den = fields.Char(related="van_ban_den_id.noi_den", string="Nơi đến ", store=True)
    
    
    
    