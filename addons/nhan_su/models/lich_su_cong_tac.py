from odoo import models, fields, api


class LichSuCongTac(models.Model):
    _name = 'lich_su_cong_tac'
    _description = 'Bảng chứa lịch sử công tác '

    chuc_vu_id = fields.Many2one("chuc_vu", string="Chức vụ")
    don_vi_id = fields.Many2one("don_vi", string="Đơn vị")
    loai_chuc_vu =fields.Selection(
        [
            ("Chính", "Chính"),
            ("Niêm nhiệm", "Niêm nhiệm")
        ],
        string="Loại chức vụ", default="Chính"
    )
    nhan_vien_id = fields.Many2one("nhan_vien", string="Nhân viên")