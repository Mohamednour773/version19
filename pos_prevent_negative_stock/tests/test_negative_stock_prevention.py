from odoo.tests import tagged
from odoo.exceptions import UserError
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestNegativeStockPrevention(TestPoSCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.config.write({
            "prevent_negative_stock": True,
            "negative_stock_check_mode": "available",
            "allow_manager_override": False,
            "block_unstorable_products": False,
        })
        cls.warehouse = cls.config.picking_type_id.warehouse_id
        cls.stock_location = cls.warehouse.lot_stock_id

        cls.product_a = cls.env["product.product"].create({
            "name": "Test Product A",
            "type": "product",
            "list_price": 10.0,
            "available_in_pos": True,
        })
        cls.service_product = cls.env["product.product"].create({
            "name": "Test Service",
            "type": "service",
            "list_price": 25.0,
            "available_in_pos": True,
        })
        cls.consumable_product = cls.env["product.product"].create({
            "name": "Test Consumable",
            "type": "consu",
            "list_price": 15.0,
            "available_in_pos": True,
        })

    def _set_stock(self, product, qty, location=None):
        location = location or self.stock_location
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()

    def _make_order_data(self, product, qty, session_id, override=False, override_uid=False):
        return {
            "data": {
                "pos_session_id": session_id,
                "partner_id": False,
                "lines": [
                    [0, 0, {
                        "product_id": product.id,
                        "qty": qty,
                        "price_unit": product.list_price,
                        "price_subtotal": product.list_price * qty,
                        "price_subtotal_incl": product.list_price * qty,
                        "discount": 0,
                        "is_negative_override": override,
                        "override_user_id": override_uid,
                        "override_reason": "Test override" if override else "",
                    }],
                ],
                "amount_total": product.list_price * qty,
                "amount_paid": product.list_price * qty,
                "amount_tax": 0,
                "amount_return": 0,
                "statement_ids": [],
                "uid": "test-order-001",
                "name": "Order test-order-001",
                "sequence_number": 1,
                "creation_date": "2026-01-01 12:00:00",
                "fiscal_position_id": False,
            },
        }

    def test_block_when_zero_stock(self):
        """Receive 5 units, sell 6 → blocked."""
        self._set_stock(self.product_a, 5)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 6, session.id)
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data, False)
        session.action_pos_session_closing_control()

    def test_allow_within_stock(self):
        """Receive 5 units, sell 5 → allowed."""
        self._set_stock(self.product_a, 5)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 5, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        session.action_pos_session_closing_control()

    def test_excluded_category_bypass(self):
        """Service product → never blocked (block_unstorable_products=False)."""
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.service_product, 100, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        session.action_pos_session_closing_control()

    def test_consumable_bypass(self):
        """Consumable product → never blocked when block_unstorable_products=False."""
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.consumable_product, 100, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        session.action_pos_session_closing_control()

    def test_block_unstorable_when_enabled(self):
        """Consumable blocked when block_unstorable_products=True and zero stock."""
        self.config.block_unstorable_products = True
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.consumable_product, 1, session.id)
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data, False)
        self.config.block_unstorable_products = False
        session.action_pos_session_closing_control()

    def test_multi_warehouse_isolation(self):
        """Stock in WH-A doesn't affect POS linked to WH-B."""
        wh_b = self.env["stock.warehouse"].create({
            "name": "Warehouse B",
            "code": "WHB",
            "company_id": self.env.company.id,
        })
        self._set_stock(self.product_a, 10, wh_b.lot_stock_id)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 1, session.id)
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data, False)
        session.action_pos_session_closing_control()

    def test_server_side_rejection(self):
        """Simulate forged frontend payload (no override flag) → server rejects."""
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 1, session.id)
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data, False)
        session.action_pos_session_closing_control()

    def test_excluded_product_bypass(self):
        """Specifically excluded products pass through."""
        self.config.excluded_product_ids = [(4, self.product_a.id)]
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 100, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        self.config.excluded_product_ids = [(3, self.product_a.id)]
        session.action_pos_session_closing_control()

    def test_excluded_category_specific(self):
        """Products in excluded category pass through."""
        self.config.excluded_product_categ_ids = [(4, self.product_a.categ_id.id)]
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 100, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        self.config.excluded_product_categ_ids = [(3, self.product_a.categ_id.id)]
        session.action_pos_session_closing_control()

    def test_negative_qty_line_ignored(self):
        """Return lines (qty < 0) should not be blocked."""
        self._set_stock(self.product_a, 0)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, -2, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        session.action_pos_session_closing_control()

    def test_on_hand_mode(self):
        """Check mode 'on_hand' uses qty_available."""
        self.config.negative_stock_check_mode = "on_hand"
        self._set_stock(self.product_a, 3)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 3, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        order_data_over = self._make_order_data(self.product_a, 50, session.id)
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data_over, False)
        self.config.negative_stock_check_mode = "available"
        session.action_pos_session_closing_control()

    def test_feature_disabled_no_block(self):
        """When prevent_negative_stock=False, no block occurs."""
        self.config.prevent_negative_stock = False
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(self.product_a, 999, session.id)
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)
        self.config.prevent_negative_stock = True
        session.action_pos_session_closing_control()
