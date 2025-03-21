from odoo import models, fields,api 

class LichLamViec(models.Model):
    _name = 'lich_lam_viec'
    _description = 'Lịch làm việc của nhân viên '
    _rec_name = 'ten_cong_viec'

    ten_cong_viec = fields.Char("Tên dự án", required=True)
    ngay_bat_dau = fields.Date("Ngày bắt đầu", required=True)
    ngay_ket_thuc = fields.Date("Ngày kết thúc")
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Nhân viên phụ trách")
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    trang_thai = fields.Selection([
        ("cho_xac_nhan", "Chờ xác nhận"),
        ("dang_thuc_hien", "Đang thực hiện"),
        ("hoan_thanh", "Hoàn thành")
    ], string="Trạng thái", default="cho_xac_nhan")
    ghi_chu = fields.Text("Ghi chú")
    cham_cong_ids = fields.One2many("bang_cham_cong",  "lich_lam_viec_id",  string="Chấm công liên quan")

    @api.constrains('tt_nhan_vien_id')
    def _check_nhan_vien_trang_thai(self):
        for record in self:
            if not record.tt_nhan_vien_id:
                continue 
            
            cham_cong = self.env['bang_cham_cong'].search([
                ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                ('trang_thai', 'in', ["Nghỉ", "Nghỉ có phép"])
            ])
            
            if cham_cong:
                raise models.ValidationError("Nhân viên đang nghỉ nên không thể có lịch làm việc.")