from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ChungChiNV(models.Model):
    _name = 'chung_chi_nv'
    _description = 'Chứng chỉ của nhân viên'
    _rec_name = 'ten_chung_chi_nv'
    
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)

    ten_chung_chi_nv = fields.Char("Tên chứng chỉ", required=True)
    loai_chung_chi_nv = fields.Selection([
        ("chuyen_mon", "Chuyên môn"),
        ("ngoai_ngu", "Ngoại ngữ"),
        ("ky_nang_mem", "Kỹ năng mềm"),
        ("khac", "Khác")
    ], string="Loại chứng chỉ", default="chuyen_mon")
    thoi_gian_cap = fields.Date("Thời gian cấp")
    ngay_het_han = fields.Date("Ngày hết hạn")
    
    @api.constrains('thoi_gian_cap', 'ngay_het_han')
    def _check_dates(self):
        for record in self:
            if record.ngay_het_han and record.thoi_gian_cap and record.ngay_het_han < record.thoi_gian_cap:
                raise ValidationError("Ngày hết hạn không được trước ngày cấp!")

