from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

class ThuongNV(models.Model):
    _name = 'thuong'
    _description = 'Xét thưởng cho nhân viên'
    _rec_name = 'ten'

    ten = fields.Char("Tiêu đề thưởng", required=True)
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", store=True)
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận")
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị")

    ly_do_thuong = fields.Text("Lý do thưởng", required=True)
    ngay_thuong = fields.Date("Ngày thưởng", required=True)
    trang_thai = fields.Selection([
        ("duyet", "Duyệt"),
        ("cho_xu_ly", "Chờ xử lý"),
        ("khong_duyet", "Không duyệt")
    ], string="Trạng thái", default="duyet")
    
    thong_ke_id = fields.Many2one("thong_ke", string="Thống kê")
    thanh_tien = fields.Float("Số tiền thưởng", required=True, default=0.0)
    ghi_chu = fields.Text("Ghi chú")

    @api.onchange("tt_nhan_vien_id")
    def _onchange_tt_nhan_vien_id(self):
        """ Khi chọn mã nhân viên, tự động điền tên, bộ phận và đơn vị """
        if self.tt_nhan_vien_id:
            self.ten_nhan_vien = self.tt_nhan_vien_id.ten_nhan_vien
            self.bo_phan_id = self.tt_nhan_vien_id.bo_phan_id
            self.don_vi_id = self.bo_phan_id.don_vi_id if self.bo_phan_id else False

    @api.constrains("thanh_tien", "ngay_thuong")
    def _check_values(self):
        """ Kiểm tra số tiền thưởng hợp lệ và ngày thưởng không vượt quá ngày hiện tại """
        for record in self:
            if record.thanh_tien < 0:
                raise ValidationError("Số tiền thưởng không thể âm!")
            if record.ngay_thuong > date.today():
                raise ValidationError("Ngày thưởng không thể là ngày trong tương lai!")
