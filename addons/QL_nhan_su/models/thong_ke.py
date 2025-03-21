from odoo import models, fields, api

class ThongKe(models.Model):
    _name = 'thong_ke'
    _description = 'Thống Kê'

    tt_nhan_vien_id = fields.Many2one("tt_nhan_vien", string="Mã nhân viên", required=True)
    ten_nhan_vien = fields.Char("Tên nhân viên", related="tt_nhan_vien_id.ten_nhan_vien", store=True)
    ngay_bat_dau = fields.Date("Ngày bắt đầu làm", related="tt_nhan_vien_id.ngay_bat_dau_lam", store=True)
    cccd = fields.Char("CCCD", related="tt_nhan_vien_id.cccd", store=True)
    email = fields.Char("Email", related="tt_nhan_vien_id.email", store=True)
    dia_chi = fields.Char("Địa chỉ", related="tt_nhan_vien_id.que_quan", store=True)
    chuc_vu = fields.Selection(related="tt_nhan_vien_id.chuc_vu", string="Chức vụ", store=True)
    bo_phan = fields.Selection("Bộ phận", related="tt_nhan_vien_id.bo_phan_id.ten_bo_phan", store=True)
    don_vi = fields.Char("Đơn vị", related="tt_nhan_vien_id.don_vi_id.ten_don_vi", store=True)

    ngay_bao_cao = fields.Date("Ngày báo cáo", default=fields.Date.today)
    ghi_chu = fields.Text("Ghi chú")

    # 🔥 Thông tin thưởng
    so_luong_thuong = fields.Integer("Số lần thưởng", compute="_compute_thong_ke", store=True)
    tong_thuong = fields.Float("Tổng tiền thưởng", compute="_compute_thong_ke", store=True)
    ly_do_thuong = fields.Text("Lý do thưởng", compute="_compute_thong_ke", store=True)
    ngay_thuong = fields.Date("Ngày thưởng", compute="_compute_thong_ke", store=True)

    # 🔥 Thống kê khác
    so_ngay_lam = fields.Integer("Số ngày làm", compute="_compute_thong_ke", store=True)
    so_ngay_nghi = fields.Integer("Số ngày nghỉ", compute="_compute_thong_ke", store=True)
    tong_gio_lam = fields.Float("Tổng giờ làm", compute="_compute_thong_ke", store=True)
    so_nhan_vien_don_vi = fields.Integer("Số nhân viên trong đơn vị", compute="_compute_thong_ke", store=True)
    so_nhan_vien_bo_phan = fields.Integer("Số nhân viên trong bộ phận", compute="_compute_thong_ke", store=True)
    so_bang_cap = fields.Integer("Bằng cấp", compute="_compute_chung_chi", store=True)
    so_chung_chi = fields.Integer("Chứng chỉ", compute="_compute_chung_chi", store=True)
    so_du_an = fields.Integer("Dự án", compute="_compute_thong_ke", store=True)
    so_bang_khen = fields.Integer("Bằng khen", compute="_compute_thong_ke", store=True)

    @api.depends('tt_nhan_vien_id', 'ngay_bao_cao')
    def _compute_thong_ke(self):
        for record in self:
            if not record.tt_nhan_vien_id or not record.ngay_bao_cao:
                continue

            ngay_bat_dau = record.ngay_bat_dau

            # 🔹 Nếu ngày báo cáo < ngày bắt đầu làm → Không tính công, thưởng
            if not ngay_bat_dau or record.ngay_bao_cao < ngay_bat_dau:
                record.so_luong_thuong = 0
                record.tong_thuong = 0
                record.ly_do_thuong = ""
                record.ngay_thuong = False
                record.so_ngay_lam = 0
                record.so_ngay_nghi = 0
                record.tong_gio_lam = 0
                continue

            # 🔹 Xử lý dữ liệu chấm công
            cham_cong_model = self.env['bang_cham_cong']
            cham_congs = cham_cong_model.search([
                ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                ('ngay_cong', '>=', ngay_bat_dau),
                ('ngay_cong', '<=', record.ngay_bao_cao)
            ])
            ngay_lam_set = set()
            ngay_nghi_set = set()
            tong_gio = 0

            for cham_cong in cham_congs:
                if cham_cong.trang_thai == 'dang_lam_viec':
                    ngay_lam_set.add(cham_cong.ngay_cong)
                    tong_gio += cham_cong.trung_binh_gio_lam
                else:
                    ngay_nghi_set.add(cham_cong.ngay_cong)

            record.so_ngay_lam = len(ngay_lam_set)
            record.so_ngay_nghi = len(ngay_nghi_set)
            record.tong_gio_lam = tong_gio

            # 🔹 Xử lý dữ liệu thưởng
            thuong_model = self.env['thuong']
            thuong_records = thuong_model.search([
                ('tt_nhan_vien_id', '=', record.tt_nhan_vien_id.id),
                ('trang_thai', '=', 'duyet'),
                ('ngay_thuong', '>=', ngay_bat_dau),
                ('ngay_thuong', '<=', record.ngay_bao_cao)
            ], order="ngay_thuong desc")

            record.so_luong_thuong = len(thuong_records)
            record.tong_thuong = sum(thuong_records.mapped('thanh_tien'))

            if thuong_records:
                record.ly_do_thuong = thuong_records[0].ly_do_thuong
                record.ngay_thuong = thuong_records[0].ngay_thuong
            else:
                record.ly_do_thuong = ""
                record.ngay_thuong = False

            if thuong_records:
                record.ly_do_thuong = thuong_records[0].ly_do_thuong
                record.ngay_thuong = thuong_records[0].ngay_thuong
            else:
                record.ly_do_thuong = ""
                record.ngay_thuong = False
                
            if record.ngay_bao_cao:
                nhan_vien_model = self.env['tt_nhan_vien']
                if record.tt_nhan_vien_id.don_vi_id:
                    record.so_nhan_vien_don_vi = nhan_vien_model.search_count([('don_vi_id', '=', record.tt_nhan_vien_id.don_vi_id.id)])
                else:
                    record.so_nhan_vien_don_vi = 0

                if record.tt_nhan_vien_id.bo_phan_id:
                    record.so_nhan_vien_bo_phan = nhan_vien_model.search_count([('bo_phan_id', '=', record.tt_nhan_vien_id.bo_phan_id.id)])
                else:
                    record.so_nhan_vien_bo_phan = 0
                    
    @api.depends('tt_nhan_vien_id')
    def _compute_chung_chi(self):
        for record in self:
            if record.tt_nhan_vien_id:
                record.so_bang_cap = len(record.tt_nhan_vien_id.trinh_do_hoc_van_ids)
                record.so_chung_chi = len(record.tt_nhan_vien_id.dao_tao_ids)