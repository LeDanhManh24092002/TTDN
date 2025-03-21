from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

class BangCapNV(models.Model):
    _name = 'bang_cap_nv'
    _description = 'Bằng cấp nhân viên '
    _rec_name = 'ten_bang_cap_nv'
    
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)

    ten_bang_cap_nv = fields.Char("Tên bằng cấp", required=True)
    truong_dao_tao = fields.Char("Trường đào tạo", required=True)
    chuyen_nganh = fields.Char("Chuyên ngành")
    hinh_thuc_dao_tao = fields.Selection([
        ("chinh_quy", "Chính quy"),
        ("tu_xa", "Từ xa"),
        ("khac", "Khác")
    ], string="Hình thức đào tạo")
    thoi_gian_cap = fields.Date("Thời gian cấp")
    
    @api.constrains('thoi_gian_cap')
    def _check_thoi_gian_cap(self):
        for record in self:
            if record.thoi_gian_cap and record.thoi_gian_cap > date.today():
                raise ValidationError("Thời gian cấp không được lớn hơn ngày hiện tại!")