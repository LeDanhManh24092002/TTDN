from odoo import models, fields, api

class KhenThuong(models.Model):
    _name = 'khen_thuong'
    _description = 'Khen thưởng của nhân viên'
    _rec_name = 'ten_bang_khen'
    
    ten_bang_khen = fields.Char("Tên bằng khen", required=True)
    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", store=True)
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị", store=True)
    thoi_gian_cap = fields.Date("Thời gian cấp", required=True)
    ly_do = fields.Char("Lý do khen thưởng")
    

