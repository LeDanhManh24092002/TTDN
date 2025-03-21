from odoo import models, fields, api
from datetime import date

class LuongNam(models.Model):
    _name = 'luong_nam'
    _description = 'Bảng lương nhân viên theo năm'
    _rec_name = 'tong_luong_nam'

    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", related="tt_nhan_vien_id.bo_phan_id", store=True)

    nam_luong = fields.Char("Năm", required=True, default=lambda self: str(date.today().year))    
    tong_luong_nam = fields.Float("Tổng lương năm", compute="_compute_tong_luong_nam", store=True)

    @api.depends('tt_nhan_vien_id', 'nam_luong')
    def _compute_tong_luong_nam(self):
        for record in self:
            if record.tt_nhan_vien_id and record.nam_luong:
                luong_thang_records = self.env['luong'].search([
                    ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                    ('thang_luong', '>=', f'{record.nam_luong}-01-01'),
                    ('thang_luong', '<=', f'{record.nam_luong}-12-31')
                ])
                record.tong_luong_nam = sum(luong_thang_records.mapped('tong_luong'))
            else:
                record.tong_luong_nam = 0
