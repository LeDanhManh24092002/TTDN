# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Google Drive™ integration',
    'version': '0.2',
    'category': 'Productivity',
    'installable': True,
    'auto_install': False,
    'data': [
        'security/ir.model.access.csv',
        'data/google_drive_data.xml',
        'views/google_drive_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'data/google_drive_demo.xml'
    ],
    'depends': ['base_setup', 'google_account'],
    'description': """
Integrate google document to Odoo record.
============================================

This module allows you to integrate google documents to any of your Odoo record quickly and easily using OAuth 2.0 for Installed Applications,
You can configure your google Authorization Code from Settings > Configuration > General Settings by clicking on "Generate Google Authorization Code"
""",
    'assets': {
        'web.assets_backend': [
            'google_drive/static/src/css/google_drive.css',
            'google_drive/static/src/js/gdrive.js',
        ],
        'web.qunit_suite_tests': [
            'google_drive/static/tests/**/*',
        ],
        'web.assets_qweb': [
            'google_drive/static/src/xml/*.xml',
        ],
    },
    'license': 'LGPL-3',
}
