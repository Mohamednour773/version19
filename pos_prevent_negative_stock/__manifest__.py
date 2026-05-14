{
    "name": "POS — Prevent Negative Stock Sales",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Block POS sales when product stock would go negative, with manager override & audit trail",
    "description": """
        Prevents POS cashiers from selling products when the resulting on-hand
        quantity in the POS-linked warehouse would drop below zero.

        Features:
        - Real-time stock check at add-to-cart, qty change, and payment validation
        - Configurable stock metric (on-hand, available, forecasted)
        - Manager PIN override with full audit logging
        - Product/category exclusions for services and consumables
        - Background stock refresh with configurable interval
        - Server-side enforcement as last line of defense
        - Full Arabic (RTL) and English support
        - Override reporting with pivot and export
    """,
    "author": "Mostafa — Odoo Functional Consultant",
    "maintainer": "Mostafa — Odoo Functional Consultant",
    "website": "",
    "license": "OPL-1",
    "depends": ["point_of_sale", "stock", "product"],
    "data": [
        "security/pos_negative_stock_security.xml",
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/pos_config_views.xml",
        "views/pos_order_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_prevent_negative_stock/static/src/scss/negative_stock.scss",
            "pos_prevent_negative_stock/static/src/app/store/pos_store.js",
            "pos_prevent_negative_stock/static/src/app/popups/negative_stock_popup.js",
            "pos_prevent_negative_stock/static/src/app/popups/negative_stock_popup.xml",
            "pos_prevent_negative_stock/static/src/app/screens/product_screen/product_screen.js",
            "pos_prevent_negative_stock/static/src/app/screens/payment_screen/payment_screen.js",
            "pos_prevent_negative_stock/static/src/app/models/pos_order.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["static/description/icon.png"],
}
