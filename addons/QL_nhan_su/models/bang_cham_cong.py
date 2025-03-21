from odoo import models, fields, api

class BangChamCong(models.Model):
    _name = 'bang_cham_cong'
    _description = 'Bảng chấm công cho nhân viên '

    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    ngay_cong = fields.Date("Ngày chấm công", required=True)
    gio_vao = fields.Float("Giờ vào")
    gio_ra = fields.Float("Giờ ra")
    trang_thai = fields.Selection([
        ("nghi", "Nghỉ "),
        ("dang_lam_viec", "Đang làm việc "),
        ("nghi_co_phep", "Nghỉ có phép ")
    ], string="Trạng thái", default="nghi")
    
    ghi_chu = fields.Char("Ghi chú")
    
    trung_binh_gio_lam = fields.Float("Trung bình giờ làm", compute="_compute_trung_binh_gio_lam")
    lich_lam_viec_id = fields.Many2one("lich_lam_viec", string="Lịch làm việc liên quan")
   
    @api.depends('gio_vao', 'gio_ra', 'trang_thai')
    def _compute_trung_binh_gio_lam(self):
        for record in self:
            if record.trang_thai == 'nghi': 
                record.gio_vao = 0
                record.gio_ra = 0
                record.trung_binh_gio_lam = 0.0
            elif record.gio_vao is not None and record.gio_ra is not None:
                record.trung_binh_gio_lam = record.gio_ra - record.gio_vao
            else:
                record.trung_binh_gio_lam = 0.0

                
