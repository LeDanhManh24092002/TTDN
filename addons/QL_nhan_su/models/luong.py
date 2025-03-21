from odoo import models, fields, api
from datetime import date, timedelta
import calendar

class LuongNhanVien(models.Model):
    _name = 'luong'
    _description = 'Bảng lương nhân viên'
    _rec_name = 'tong_luong'

    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", related="tt_nhan_vien_id.bo_phan_id", store=True)
    thang_luong = fields.Date("Tháng lương", required=True)
    ten_thang = fields.Char("Tên tháng",  compute="_compute_ten_thang", store=True)

    luong_co_ban = fields.Float("Lương cơ bản", compute="_compute_luong_co_ban", store=True)
    phu_cap = fields.Float("Phụ cấp", compute="_compute_phu_cap", store=True)
    
    bao_hiem_id = fields.Many2one("bao_hiem", string="Bảo hiẻm ", related="tt_nhan_vien_id.bao_hiem_id", store=True)
    muc_dong = fields.Float("Mức đóng", compute="_compute_muc_dong", store=True)
    
    thuong = fields.Float("Thưởng", compute="_compute_thuong", store=True, default=0.0)
    khau_tru = fields.Float("Khấu trừ", default=0.0)
    luong_chuyen_can = fields.Float("Lương chuyên cần", compute="_compute_luong_chuyen_can", store=True)
    tong_luong = fields.Float("Tổng lương thực nhận", compute="_compute_tong_luong", store=True)

    @api.depends('thang_luong')
    def _compute_ten_thang(self):
        for record in self:
            if record.thang_luong:
                record.ten_thang = record.thang_luong.strftime('%m/%Y')
            else:
                record.ten_thang = ''

    @api.depends('bo_phan_id')
    def _compute_luong_co_ban(self):
        for record in self:
            record.luong_co_ban = record.bo_phan_id.luong_co_ban if record.bo_phan_id else 0.0

    @api.depends('bo_phan_id')
    def _compute_phu_cap(self):
        for record in self:
            record.phu_cap = record.bo_phan_id.phu_cap if record.bo_phan_id else 0.0
            
    @api.depends('bao_hiem_id')
    def _compute_muc_dong(self):
        for record in self:
            record.muc_dong = record.bao_hiem_id.muc_dong if record.bao_hiem_id else 0.0
            
    @api.depends('tt_nhan_vien_id', 'thang_luong')
    def _compute_thuong(self):
        for record in self:
            if record.tt_nhan_vien_id and record.thang_luong:
                year = record.thang_luong.year
                month = record.thang_luong.month
                ngay_bat_dau = date(year, month, 1)
                ngay_cuoi_thang = date(year, month, calendar.monthrange(year, month)[1])
                
                cham_cong_records = self.env['bang_cham_cong'].search_count([
                ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                ('ngay_cong', '>=', ngay_bat_dau),
                ('ngay_cong', '<=', ngay_cuoi_thang)
                ])

                if cham_cong_records == 0:
                    record._reset_values()
                    continue

                # Nếu có dữ liệu chấm công, tính toán các giá trị
                record.luong_co_ban = record.bo_phan_id.luong_co_ban if record.bo_phan_id else 0.0
                record.phu_cap = record.bo_phan_id.phu_cap if record.bo_phan_id else 0.0
                record.muc_dong = record.bao_hiem_id.muc_dong if record.bao_hiem_id else 0.0

                thuong_records = self.env['thuong'].search([
                    ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                    ('ngay_thuong', '>=', ngay_bat_dau),
                    ('ngay_thuong', '<=', ngay_cuoi_thang),
                    ('trang_thai', '=', 'duyet')
                ])

                record.thuong = sum(thuong_records.mapped('thanh_tien'))
            else:
                record.thuong = 0.0

    @api.depends('tt_nhan_vien_id', 'thang_luong')
    def _compute_luong_chuyen_can(self):
        for record in self:
            if record.tt_nhan_vien_id and record.thang_luong:
                year = record.thang_luong.year
                month = record.thang_luong.month
                ngay_bat_dau = date(year, month, 1)
                ngay_cuoi_thang = date(year, month, calendar.monthrange(year, month)[1]) 

                bang_cham_cong_records = self.env['bang_cham_cong'].search([
                    ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                    ('ngay_cong', '>=', ngay_bat_dau),
                    ('ngay_cong', '<=', ngay_cuoi_thang),
                    ('trang_thai', 'in', ['nghi', 'nghi_co_phep'])
                ])

                so_ngay_nghi = len(bang_cham_cong_records)
                so_gio_nghi = sum(bang_cham_cong_records.mapped('trung_binh_gio_lam'))

                if so_ngay_nghi > 2 or so_gio_nghi > 48:
                    record.luong_chuyen_can = 0.0
                else:
                    record.luong_chuyen_can = 500000.0 
            else:
                record.luong_chuyen_can = 0.0

    @api.depends('luong_co_ban', 'phu_cap', 'thuong', 'khau_tru', 'luong_chuyen_can', 'muc_dong')
    def _compute_tong_luong(self):
        for record in self:
            record.tong_luong = (
                record.luong_co_ban +
                record.phu_cap +
                record.thuong +
                record.luong_chuyen_can -
                record.khau_tru -
                record.muc_dong
            )
            
    def _reset_values(self):
        """Đặt lại các giá trị về 0 nếu không có dữ liệu chấm công"""
        self.luong_co_ban = 0.0
        self.phu_cap = 0.0
        self.muc_dong = 0.0
        self.thuong = 0.0
        self.luong_chuyen_can = 0.0
        self.tong_luong = 0.0
