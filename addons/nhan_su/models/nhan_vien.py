from odoo import models, fields, api
from datetime import date
from odoo.exceptions import ValidationError


class NhanVien(models.Model):
    _name = 'nhan_vien'
    _description = 'Bảng chứa thông tin nhân viên'
    _rec_name = 'ten_nhan_vien'
    #_order = 'ten_nhan_vien asc, tuoi desc'
    
    ma_dinh_danh = fields.Char("Mã định danh", required=True)
    ten_nhan_vien = fields.Char("Ten nhan vien")
    ngay_sinh = fields.Date("Ngày sinh")
    que_quan = fields.Char("Quê quán")
    email = fields.Char("Email")
    so_dien_thoai = fields.Char("Số điện thoại")
    lich_su_cong_tac_ids = fields.One2many(
        "lich_su_cong_tac", 
        inverse_name="nhan_vien_id",
        string= "Danh sach lich su cong tac")
    tuoi = fields.Integer("Tuổi", compute="_compute_tinh_tuoi", store=True)
    anh = fields.Binary("Anh")
    
    danh_sach_bang_cap_ids = fields.One2many(
        "danh_sach_bang_cap", 
        inverse_name="nhan_vien_id",
        string= "Danh sach bang cap")
    
    @api.depends('ngay_sinh')
    def _compute_tinh_tuoi(self):
        for record in self:
            if record.ngay_sinh:
                today = date.today()
                record.tuoi = today.year - record.ngay_sinh.year
                record.tuoi
            else:
                record.tuoi = 0
                
    @api.constrains('tuoi')
    def  _check_tuoi(self):
        for record in self:
            if record.tuoi < 18:
                raise ValidationError("Tuổi phải lớn hon 18 ")
                