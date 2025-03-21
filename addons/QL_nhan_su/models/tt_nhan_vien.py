from odoo import models, fields, api
from datetime import date
from odoo.exceptions import ValidationError
import re

class ThongTinNhanVien(models.Model):
    _name = 'tt_nhan_vien'
    _description = 'Thông tin nhân viên'
    _rec_name = 'ma_nhan_vien'

    # Thông tin cá nhân
    ma_nhan_vien = fields.Char("Mã định danh", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", required=True)
    ngay_sinh = fields.Date("Ngày sinh", required=True)
    tuoi = fields.Integer("Tuổi", compute="_compute_tinh_tuoi", store=True)
    que_quan = fields.Char("Địa chỉ", required=True)
    email = fields.Char("Email", required=True)
    lien_lac = fields.Char("Số liên lạc", required=True)
    cccd = fields.Char("Căn cước công dân", required=True)
    ngay_bat_dau_lam = fields.Date("Ngày bắt đầu làm việc", required=True)
    anh = fields.Binary("Ảnh", store=True)
    
    trang_thai = fields.Selection([
        ('dang_lam', 'Đang làm'),
        ('nghi', 'Nghỉ'),
        ('nghi_phep', 'Nghỉ có phép')
    ], string="Trạng thái", default='dang_lam')

    # Thông tin nơi làm việc
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị")
    bo_phan_id = fields.Many2one("bo_phan", string="Bộ phận", domain="[('don_vi_id', '=', don_vi_id)]")  
    bao_hiem_id = fields.Many2one("bao_hiem", string="Bảo Hiểm")

    # Các thông tin liên quan
    ten_don_vi = fields.Char(related="don_vi_id.ten_don_vi", string="Tên đơn vị", store=True, )
    ten_bo_phan = fields.Selection(related="bo_phan_id.ten_bo_phan", string="Tên bộ phận", store=True)
    ten_bao_hiem = fields.Char(related="bao_hiem_id.ten_bao_hiem", string="Tên bảo hiểm", store=True)
    muc_dong = fields.Float(related="bao_hiem_id.muc_dong", string="Mức đóng", store=True)

    # Thông tin gia đình
    ten_cha = fields.Char("Tên bố")
    nghe_cha = fields.Char("Nghề nghiệp bố")
    so_dien_thoai_cha = fields.Char("Số điện thoại bố")
    ten_me = fields.Char("Tên mẹ")
    nghe_me = fields.Char("Nghề nghiệp mẹ")
    so_dien_thoai_me = fields.Char("Số điện thoại mẹ")
    vo = fields.Char("Vợ (nếu có)")
    so_dien_thoai_vo = fields.Char("Số điện thoại vợ (nếu có)")
    con_cai = fields.Char("Con cái (nếu có)")
    
    chuc_vu = fields.Selection([
        ('giam_doc', 'Giám đốc'),
        ('pho_giam_doc', 'Phó giám đốc'),
        ('truong_phong', 'Trưởng phòng'),
        ('pho_phong', 'Phó phòng'),
        ('nhan_vien', 'Nhân viên')
    ], string="Chức vụ", required=True, default='nhan_vien')
    
    lich_lam_viec_ids = fields.One2many("lich_lam_viec","tt_nhan_vien_id",  string="Lịch làm việc")
    luong_ids = fields.One2many("luong","tt_nhan_vien_id",  string="Lương")
    trinh_do_hoc_van_ids = fields.One2many("trinh_do_hoc_van","tt_nhan_vien_id", string="Trình độ học vấn")
    dao_tao_ids = fields.One2many("dao_tao","tt_nhan_vien_id",  string="Đào tạo" )
    luong_nam_ids = fields.One2many("luong_nam","tt_nhan_vien_id",  string="Lương năm")
    khen_thuong_ids = fields.One2many("khen_thuong","tt_nhan_vien_id",  string="Khen thưởng")
    cong_viec_ids = fields.One2many("cong_viec","tt_nhan_vien_id",  string="Thông tin công việc")
    thuong_ids = fields.One2many("thuong", "tt_nhan_vien_id", string="Thưởng ")

    @api.depends('ngay_sinh')
    def _compute_tinh_tuoi(self):
        for record in self:
            if record.ngay_sinh:
                today = date.today()
                record.tuoi = today.year - record.ngay_sinh.year
            else:
                record.tuoi = 0

    @api.constrains('tuoi', 'ten_nhan_vien', 'lien_lac', 'cccd', 'ngay_bat_dau_lam', 'email')
    def _check_constrains(self):
        for record in self:
            if record.tuoi < 18:
                raise ValidationError("Tuổi phải lớn hơn 18")
            
            if not re.match(r'^[a-zA-ZÀ-Ỹà-ỹ\s]+$', record.ten_nhan_vien):
                raise ValidationError("Tên nhân viên không được chứa ký tự đặc biệt hoặc số!")
            
            if not record.lien_lac.isdigit() or len(record.lien_lac) != 10:
                raise ValidationError("Số điện thoại phải có đúng 10 số và chỉ chứa chữ số!")
            
            if not record.cccd.isdigit() or len(record.cccd) != 12:
                raise ValidationError("Căn cước công dân phải có đúng 12 số!")
            
            if self.search_count([('cccd', '=', record.cccd)]) > 1:
                raise ValidationError("Căn cước công dân đã tồn tại!")
            
            if self.search_count([('email', '=', record.email)]) > 1:
                raise ValidationError("Email này đã tồn tại trong hệ thống!")
            
            if self.search_count([('lien_lac', '=', record.lien_lac)]) > 1:
                raise ValidationError("Số điện thoại này đã được sử dụng!")
            
            if record.ngay_bat_dau_lam < record.ngay_sinh:
                raise ValidationError("Ngày bắt đầu làm việc không được trước ngày sinh!")
            
            if record.tuoi < 18 and record.ngay_bat_dau_lam:
                raise ValidationError("Nhân viên dưới 18 tuổi không thể có ngày bắt đầu làm việc!")

    @api.onchange('don_vi_id')
    def _onchange_don_vi(self):
        self.bo_phan_id = False
