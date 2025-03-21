from odoo import models, fields, api

class CongViec(models.Model):
    _name = 'cong_viec'
    _description = 'Thông tin công việc của nhân viên'

    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", related="tt_nhan_vien_id.bo_phan_id", store=True)
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị", related="tt_nhan_vien_id.don_vi_id", store=True)

    ngay_bat_dau = fields.Date("Ngày bắt đầu làm việc", related="tt_nhan_vien_id.ngay_bat_dau_lam", store=True)
    trang_thai = fields.Selection([
        ('dang_lam', 'Đang làm việc'),
        ('tam_nghi', 'Tạm nghỉ'),
        ('thoi_viec', 'Thôi việc')
    ], string="Trạng thái", required=True, default='dang_lam')

    luong_co_ban = fields.Float(string="Lương cơ bản", related="bo_phan_id.luong_co_ban", store=True)
    phu_cap = fields.Float(string="Phụ cấp", related="bo_phan_id.phu_cap", store=True)

