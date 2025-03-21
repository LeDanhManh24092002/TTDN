from odoo import models, fields

class DaoTao(models.Model):
    _name = 'dao_tao'
    _description = 'Đào tạo nhân viên'
    _rec_name = 'tieu_muc'
    
    tieu_muc = fields.Char("Tiêu mục", required=True)
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", store=True)
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị", store=True)
    noi_dung = fields.Char("Nội dung")
