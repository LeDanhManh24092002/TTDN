# -*- coding: utf-8 -*-
{
    'name': 'test-inherit',
    'version': '0.1',
    'category': 'Hidden/Tests',
    'description': """A module to verify the inheritance.""",
    'depends': ['base', 'test_new_api'],
    'data': [
        'ir.model.access.csv',
        'demo_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
