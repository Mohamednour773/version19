{
    'name': 'Inter-Branch Stock Request',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Inter-branch stock requests with dispatch, receipt, and return lifecycle',
    'description': """
Inter-branch stock request workflow for Odoo 19.

Features:
- Branch-to-branch stock requests
- Linked outgoing and incoming pickings
- Partial dispatch and receipt handling
- Return wizard with reverse pickings
- Dynamic request and return status tracking
    """,
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock', 'mail'],
    'data': [
        'security/stock_request_security.xml',
        'security/ir.model.access.csv',
        'data/stock_request_sequence.xml',
        'wizard/stock_request_return_wizard_views.xml',
        'views/stock_request_views.xml',
        'views/stock_picking_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'application': False,
}
