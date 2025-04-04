# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Attendances',
    'version': '2.0',
    'category': 'Human Resources/Attendances',
    'sequence': 240,
    'summary': 'Track employee attendance',
    'description': """
This module aims to manage employee's attendances.
==================================================

Keeps account of the attendances of the employees on the basis of the
actions(Check in/Check out) performed by them.
       """,
    'website': 'https://www.odoo.com/app/employees',
    'depends': ['hr', 'barcodes'],
    'data': [
        'security/hr_attendance_security.xml',
        'security/ir.model.access.csv',
        'views/hr_attendance_view.xml',
        'views/hr_attendance_overtime_view.xml',
        'report/hr_attendance_report_views.xml',
        'views/hr_department_view.xml',
        'views/hr_employee_view.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'data/hr_attendance_demo.xml'
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'assets': {
        'web.assets_backend': [
            'hr_attendance/static/src/js/employee_kanban_view_handler.js',
            'hr_attendance/static/src/js/greeting_message.js',
            'hr_attendance/static/src/js/kiosk_mode.js',
            'hr_attendance/static/src/js/kiosk_confirm.js',
            'hr_attendance/static/src/js/my_attendances.js',
            'hr_attendance/static/src/js/time_widget.js',
            'hr_attendance/static/src/scss/hr_attendance.scss',
        ],
        'web.qunit_suite_tests': [
            ('after', 'web/static/tests/legacy/views/kanban_tests.js', 'hr_attendance/static/tests/hr_attendance_tests.js'),
        ],
        'web.assets_qweb': [
            'hr_attendance/static/src/xml/**/*',
        ],
    },
    'license': 'LGPL-3',
}
