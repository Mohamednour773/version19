# -*- coding: utf-8 -*-
{
    'name': 'Factory Base | الأساس للمصنع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Base module for project-based factory ERP | الموديول الأساسي لنظام إدارة المصنع القائم على المشاريع',
    'description': """
Factory Base Module
===================
Provides the foundational data structures for a project-based manufacturing ERP:
- Project sectors (قطاعات المشروع)
- Manufacturing stages (مراحل التصنيع)
- Shared configuration and master data
- Multi-language support (Arabic / English)
    """,
    'author': 'Manufacturing ERP Team',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'product',
        'stock',
        'account',
        'project',
        'analytic',
        'uom',
    ],
    'data': [
        'security/factory_security.xml',
        'security/ir.model.access.csv',
        'data/factory_sequences.xml',
        'data/factory_stages_data.xml',
        'views/factory_sector_views.xml',
        'views/factory_stage_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/factory_menus.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
