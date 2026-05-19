# -*- coding: utf-8 -*-
{
    'name': 'Factory Site Delivery & Installation | توريد وتركيب الموقع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Loading permits, delivery notes, site installation and finishing | أذون التحميل والتوريد والتركيب والتشطيب بالموقع',
    'description': """
Site Delivery & Installation
============================
- Loading permits | أذون التحميل
- Delivery permits | أذون التوريد
- Track delivered quantities and damaged-in-transit | تتبع الكميات الموردة والتالف أثناء النقل
- Site installation orders with accessories consumption (tish, nails, brackets, angles, chemicals) | أوامر التركيب بالموقع مع استهلاك الإكسسوارات
- Site finishing with materials (sefito, epoxy, paint) | التشطيب بالموقع مع الخامات
- Daily site expenses | المصروفات اليومية للموقع
- Auto-allocation of all costs to project & analytic | توزيع تلقائي للتكاليف على المشروع والحساب التحليلي
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'factory_production',
        'stock',
        'hr_expense',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/site_sequences.xml',
        'views/factory_loading_permit_views.xml',
        'views/factory_delivery_permit_views.xml',
        'views/factory_installation_views.xml',
        'views/factory_site_expense_views.xml',
        'views/factory_sector_views_inherit.xml',
        'views/factory_site_menus.xml',
    ],
    'application': False,
    'installable': True,
}
