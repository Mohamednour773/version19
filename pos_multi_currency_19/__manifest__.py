{
    "name": "POS Multi Currency Payments",
    "summary": "Accept and audit POS payments in foreign currencies for Odoo 19.",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Mostafa / Codex",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account"],
    "data": [
        "views/pos_config_views.xml",
        "views/pos_payment_views.xml",
        "views/pos_session_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_multi_currency_19/static/src/js/pos_multi_currency.js",
            "pos_multi_currency_19/static/src/xml/pos_multi_currency.xml",
            "pos_multi_currency_19/static/src/scss/pos_multi_currency.scss",
        ],
    },
    "installable": True,
    "application": False,
}

