from odoo import models, fields, api

class TrinhDoHocVan(models.Model):
    _name = 'trinh_do_hoc_van'
    _description = 'Trình độ học vấn của nhân viên'
    
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)

    bang_cap_nv_id = fields.Many2one("bang_cap_nv", string="Bằng cấp")
    chung_chi_nv_id = fields.Many2one("chung_chi_nv", string="Chứng chỉ")

    # Thông tin BẰNG CẤP lấy từ bảng bang_cap_nv
    ten_bang_cap_nv = fields.Char("Tên bằng cấp", related="bang_cap_nv_id.ten_bang_cap_nv", store=True)
    truong_dao_tao = fields.Char("Trường đào tạo", related="bang_cap_nv_id.truong_dao_tao", store=True)
    chuyen_nganh = fields.Char("Chuyên ngành", related="bang_cap_nv_id.chuyen_nganh", store=True)
    hinh_thuc_dao_tao = fields.Selection([
        ("chinh_quy", "Chính quy"),
        ("tu_xa", "Từ xa"),
        ("khac", "Khác")
    ], string="Hình thức đào tạo", related="bang_cap_nv_id.hinh_thuc_dao_tao", store=True)
    thoi_gian_cap_bang_cap = fields.Date("Thời gian cấp bằng cấp", related="bang_cap_nv_id.thoi_gian_cap", store=True)

    # Thông tin CHỨNG CHỈ lấy từ bảng chung_chi_nv
    ten_chung_chi_nv = fields.Char("Tên chứng chỉ", related="chung_chi_nv_id.ten_chung_chi_nv", store=True)
    loai_chung_chi_nv = fields.Selection([
        ("chuyen_mon", "Chuyên môn"),
        ("ngoai_ngu", "Ngoại ngữ"),
        ("ky_nang_mem", "Kỹ năng mềm"),
        ("khac", "Khác")
    ], string="Loại chứng chỉ", related="chung_chi_nv_id.loai_chung_chi_nv", store=True)
    thoi_gian_cap_chung_chi = fields.Date("Thời gian cấp chứng chỉ", related="chung_chi_nv_id.thoi_gian_cap", store=True)
    ngay_het_han = fields.Date("Ngày hết hạn", related="chung_chi_nv_id.ngay_het_han", store=True)

    @api.depends('tt_nhan_vien_id')
    def _compute_bang_cap_chung_chi(self):
        """Tự động lấy danh sách bằng cấp và chứng chỉ khi chọn Mã nhân viên"""
        for record in self:
            if record.tt_nhan_vien_id:
                record.bang_cap_ids = self.env['bang_cap_nv'].search([('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id)])
                record.chung_chi_ids = self.env['chung_chi_nv'].search([('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id)])
            else:
                record.bang_cap_ids = False
                record.chung_chi_ids = False
