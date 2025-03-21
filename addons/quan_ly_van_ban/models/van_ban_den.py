from odoo import models, fields, api
from datetime import date


class VanBanDen(models.Model):
    _name = 'van_ban_den'
    _description = 'Văn bản đến'
    _rec_name = 'ten_van_ban'

    ma_van_ban_den = fields.Char("Mã Văn Bản Đến", required=True)
    ten_van_ban = fields.Char("Tên Văn Bản", required=True)
    noi_den = fields.Char("Nơi Đến")
    ngay_nhan = fields.Date("Ngày Nhận", default=date.today())
    nguoi_nhan = fields.Char("Người nhận ")
    ghi_chu = fields.Text("Ghi Chú")
    trang_thai =fields.Selection(
        [
            ("Đã gửi ", "Đã gửi "),
            ("Nháp ", "Nháp ")
        ],
        string="Trạng thái ", default="Nháp "
    )
    danh_sach_van_ban_den_ids = fields.Many2one(
        "danh_sach_van_ban_den", 
        inverse_name="van_ban_den_id",
        string= "Danh sách văn bản đến ")
    
    loai_van_ban_ids = fields.Many2one(
        "loai_van_ban", 
        inverse_name="van_ban_den_id",
        string= "Loại văn bản đến ")
    
    loai = fields.Selection(related="loai_van_ban_ids.loai", string="Loại ", store=True)
    
    
   
