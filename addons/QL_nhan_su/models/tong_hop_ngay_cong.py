from odoo import models, fields

class TongHopNgayCong(models.Model):
    _name = 'tong_hop_ngay_cong'
    _description = 'Thống Kê'

    name = fields.Char("Tên báo cáo", required=True)
    ngay_tao = fields.Date("Ngày tạo", default=fields.Date.today)
    ghi_chu = fields.Text("Ghi chú")
