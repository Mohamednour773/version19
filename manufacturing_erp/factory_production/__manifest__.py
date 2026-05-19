# -*- coding: utf-8 -*-
{
    'name': 'Factory Production | إنتاج المصنع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Production orders with multi-stage tracking and per-stage costing | أوامر الإنتاج بتتبع المراحل والتكلفة لكل مرحلة',
    'description': """
Factory Production
==================
- Custom production orders per sector
- Multi-stage workflow (mold prep → casting → demolding → curing → finishing → storage)
- Mold usage registration per production
- Mix consumption tracking
- Labor and time tracking per stage
- Waste/loss tracking per stage and material
- Auto-update of sector produced quantities

أوامر إنتاج مخصصة لكل قطاع، تدفق متعدد المراحل، تسجيل استخدام القوالب،
تتبع استهلاك الخلطات، تتبع العمالة والوقت لكل مرحلة، تتبع الهالك،
وتحديث كميات القطاع المنتجة تلقائياً.
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'factory_molds',
        'factory_mix_design',
        'mrp',
        'stock',
        'hr_timesheet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/production_sequences.xml',
        'views/factory_production_views.xml',
        'views/factory_production_stage_views.xml',
        'views/factory_sector_views_inherit.xml',
        'views/factory_production_menus.xml',
    ],
    'application': False,
    'installable': True,
}
