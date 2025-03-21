from odoo import models, fields, api


class DanhSachBangCap(models.Model):
    _name = 'danh_sach_bang_cap'
    _description = 'Bảng chứa danh sach bang cap '

    bang_cap_id = fields.Many2one("bang_cap", string="Bang cap")
    chung_chi_id = fields.Many2one("chung_chi", string="Chung chi")
    nhan_vien_id = fields.Many2one("nhan_vien", string="Nhân viên")
    ma_dinh_danh = fields.Char("Ma dinh danh", related='nhan_vien_id.ma_dinh_danh')