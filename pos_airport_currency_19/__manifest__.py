{
    "name": "POS Airport Multi-Currency",
    "summary": "Airport POS sale currencies, physical tender tracking, and AED-safe accounting.",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Codex",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account"],
    "data": [
        "views/pos_config_views.xml",
        "views/res_config_settings_views.xml",
        "views/pos_payment_method_views.xml",
        "views/pos_payment_views.xml",
        "views/pos_order_views.xml",
        "views/pos_session_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_airport_currency_19/static/src/js/airport_currency.js",
            "pos_airport_currency_19/static/src/xml/airport_currency.xml",
            "pos_airport_currency_19/static/src/scss/airport_currency.scss",
        ],
    },
    "installable": True,
    "application": False,
}
