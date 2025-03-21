from odoo import models, fields, api
from odoo.exceptions import ValidationError

class BoPhan(models.Model):
    _name = 'bo_phan'
    _description = 'Bộ phận nhân viên trực thuộc '
    _rec_name = 'ten_bo_phan'

    don_vi_id = fields.Many2one("don_vi", string="Đơn vị")
    
    ten_bo_phan = fields.Selection(
        [
            ("san_xuat", "Sản xuất "),
            ("nhan_su", "Nhân sự "),
            ("sale", "Sale "),
            ("tuyen_dung", "Tuyển dụng "),
            ("hieu_chuan", "Hiệu chuẩn "),
            ("it", "IT ")
        ],
        string="Tên bộ phận ", default="it"
    )
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True, domain="[('chuc_vu', 'in', ['truong_phong', 'pho_giam_doc', 'giam_doc'])]")
    
    # Lấy tên nhân viên & chức vụ từ model tt_nhan_vien
    ten_nhan_vien = fields.Char(string="Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    chuc_vu = fields.Selection(string="Chức vụ", related="tt_nhan_vien_id.chuc_vu", store=True)

    # Ràng buộc: Chỉ nhận nhân viên có chức vụ từ "Trưởng phòng" trở lên
    @api.constrains("tt_nhan_vien_id")
    def _check_chuc_vu(self):
        chuc_vu_hop_le = ["truong_phong", "pho_giam_doc", "giam_doc"]  # Phải khớp với selection của tt_nhan_vien
        for record in self:
            if record.tt_nhan_vien_id and record.tt_nhan_vien_id.chuc_vu not in chuc_vu_hop_le:
                raise ValidationError("Người phụ trách phải có chức vụ từ 'Trưởng phòng' trở lên!")
    luong_co_ban = fields.Float("Lương cơ bản", required=True, default=0.0)
    phu_cap = fields.Float("Phụ cấp", default=0.0)

    @api.constrains("luong_co_ban", "phu_cap")
    def _check_salary_values(self):
        for rec in self:
            if rec.luong_co_ban < 0:
                raise ValidationError("Lương cơ bản không thể nhỏ hơn 0!")
            if rec.phu_cap < 0:
                raise ValidationError("Phụ cấp không thể nhỏ hơn 0!")

    _sql_constraints = [
        ('unique_bo_phan_don_vi', 'unique(ten_bo_phan, don_vi_id)', 'Bộ phận này đã tồn tại trong đơn vị!')
    ]