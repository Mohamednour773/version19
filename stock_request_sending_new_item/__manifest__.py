{
    'name': 'Stock Request Sending New Item',
    'version': '19.0.1.0.0',
    'summary': 'Inter-branch stock transfer requests with two-step picking',
    'description': 'Allows users to create stock transfer requests between warehouses using an intermediate transit location.',
    'category': 'Warehouse',
    'author': 'Antigravity',
    'depends': ['stock', 'uom'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/stock_request_sending_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
