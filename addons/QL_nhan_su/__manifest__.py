# -*- coding: utf-8 -*-
{
    'name': "QL_nhan_su",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "QL_nhan_su",
    'website': "http://localhost:8069/web",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/tt_nhan_vien.xml',
        'views/don_vi.xml',
        'views/bo_phan.xml',
        'views/bang_cham_cong.xml',
        'views/lich_lam_viec.xml',
        'views/cong_viec.xml',
        'views/bang_cap_nv.xml',
        'views/chung_chi_nv.xml',
        'views/khen_thuong.xml',
        'views/trinh_do_hoc_van.xml',
        'views/luong.xml',
        'views/luong_nam.xml',
        'views/thuong.xml',
        'views/bao_hiem.xml',
        'views/dao_tao.xml',
        'views/thong_ke.xml',
        'views/menu.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
