# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Pad on tasks',
    'category': 'Services/Project',
    'description': """
This module adds a PAD in all project form views.
=================================================
    """,
    'depends': [
        'project',
        'pad'
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/project_views.xml',
        ],
    'auto_install': True,
    'assets': {
        'web.assets_frontend': [
            'pad_project/static/**/*',
        ],
    },
    'license': 'LGPL-3',
}
