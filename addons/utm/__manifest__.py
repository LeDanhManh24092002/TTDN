# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'UTM Trackers',
    'category': 'Hidden',
    'description': """
Enable management of UTM trackers: campaign, medium, source.
""",
    'version': '1.1',
    'depends': ['base', 'web'],
    'data': [
        'data/utm_data.xml',
        'views/utm_campaign_views.xml',
        'views/utm_views.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [
        'data/utm_demo.xml',
    ],
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            'utm/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}
