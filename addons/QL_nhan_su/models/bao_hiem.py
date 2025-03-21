from odoo import models, fields, api
from datetime import date

class BaoHiemLD(models.Model):
    _name = 'bao_hiem'
    _description = 'Bảo hiểm lao động cho nhân viên'
    _rec_name = 'ten_bao_hiem'

    ten_bao_hiem = fields.Char("Tên bảo hiểm", required=True)
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", related="tt_nhan_vien_id.bo_phan_id", store=True)
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị", related="tt_nhan_vien_id.don_vi_id", store=True)
    
    loai_bao_hiem = fields.Selection([
        ("y_te", "Bảo hiểm y tế"),
        ("xa_hoi", "Bảo hiểm xã hội"),
        ("that_nghiep", "Bảo hiểm thất nghiệp"),
    ], string="Loại bảo hiểm", required=True)
    
    tu_ngay = fields.Date("Ngày gia hạn", required=True)
    den_ngay = fields.Date("Ngày hết hạn")
    muc_dong = fields.Float("Mức đóng")
    trang_thai = fields.Selection([
        ("hieu_luc", "Hiệu lực"),
        ("het_han", "Hết hạn"),
        ("tam_ngung", "Tạm ngưng"),
    ], string="Trạng thái", default="hieu_luc", compute="_compute_trang_thai", store=True)
    ghi_chu = fields.Text("Ghi chú")
    
    @api.depends('den_ngay')
    def _compute_trang_thai(self):
        for record in self:
            if record.den_ngay and record.den_ngay < date.today():
                record.trang_thai = "het_han"
            else:
                record.trang_thai = "hieu_luc"


