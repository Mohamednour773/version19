from odoo.tests import tagged
from odoo.exceptions import UserError
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestOverrideFlow(TestPoSCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.override_group = cls.env.ref(
            "pos_prevent_negative_stock.group_pos_negative_stock_override"
        )
        cls.config.write({
            "prevent_negative_stock": True,
            "negative_stock_check_mode": "available",
            "allow_manager_override": True,
            "override_user_group_id": cls.override_group.id,
            "block_unstorable_products": False,
        })
        cls.warehouse = cls.config.picking_type_id.warehouse_id
        cls.stock_location = cls.warehouse.lot_stock_id

        cls.product_a = cls.env["product.product"].create({
            "name": "Override Test Product",
            "type": "product",
            "list_price": 10.0,
            "available_in_pos": True,
        })

        cls.manager_user = cls.env["res.users"].create({
            "name": "Test Manager",
            "login": "test_manager_override",
            "groups_id": [(4, cls.override_group.id)],
        })
        cls.regular_user = cls.env["res.users"].create({
            "name": "Test Cashier",
            "login": "test_cashier_no_override",
            "groups_id": [(4, cls.env.ref("point_of_sale.group_pos_user").id)],
        })

    def _set_stock(self, product, qty, location=None):
        location = location or self.stock_location
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()

    def _make_order_data(self, product, qty, session_id, override=False,
                         override_uid=False, reason=""):
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
                        "override_reason": reason,
                    }],
                ],
                "amount_total": product.list_price * qty,
                "amount_paid": product.list_price * qty,
                "amount_tax": 0,
                "amount_return": 0,
                "statement_ids": [],
                "uid": "test-override-001",
                "name": "Order test-override-001",
                "sequence_number": 1,
                "creation_date": "2026-01-01 12:00:00",
                "fiscal_position_id": False,
            },
        }

    def test_allow_with_override(self):
        """Override by authorized manager → success + log entry."""
        self._set_stock(self.product_a, 5)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(
            self.product_a, 6, session.id,
            override=True,
            override_uid=self.manager_user.id,
            reason="Customer prepaid, stock arriving tomorrow",
        )
        order = self.env["pos.order"]._process_order(order_data, False)
        self.assertTrue(order)

        override_lines = self.env["pos.order.line"].search([
            ("order_id", "=", order),
            ("is_negative_override", "=", True),
        ])
        self.assertTrue(len(override_lines) >= 1)
        line = override_lines[0]
        self.assertEqual(line.override_user_id.id, self.manager_user.id)
        self.assertEqual(line.override_reason, "Customer prepaid, stock arriving tomorrow")
        session.action_pos_session_closing_control()

    def test_reject_unauthorized_override(self):
        """Override by unauthorized user → rejected."""
        self._set_stock(self.product_a, 5)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(
            self.product_a, 6, session.id,
            override=True,
            override_uid=self.regular_user.id,
        )
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data, False)
        session.action_pos_session_closing_control()

    def test_override_disabled_always_blocks(self):
        """When allow_manager_override=False, override flag is ignored server-side."""
        self.config.allow_manager_override = False
        self._set_stock(self.product_a, 5)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(
            self.product_a, 6, session.id,
            override=True,
            override_uid=self.manager_user.id,
        )
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data, False)
        self.config.allow_manager_override = True
        session.action_pos_session_closing_control()

    def test_stock_levels_rpc_batch(self):
        """Batch RPC returns correct stock for multiple products."""
        self._set_stock(self.product_a, 42)
        product_b = self.env["product.product"].create({
            "name": "Product B RPC",
            "type": "product",
            "list_price": 20.0,
        })
        self._set_stock(product_b, 7)

        result = self.env["pos.session"].get_product_stock_levels(
            [self.product_a.id, product_b.id],
            self.warehouse.id,
        )
        self.assertIn(self.product_a.id, result)
        self.assertIn(product_b.id, result)
        self.assertEqual(result[self.product_a.id]["on_hand"], 42)
        self.assertEqual(result[product_b.id]["on_hand"], 7)

    def test_override_audit_report_data(self):
        """Override entries appear in the reporting action domain."""
        self._set_stock(self.product_a, 0)
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
        })
        order_data = self._make_order_data(
            self.product_a, 1, session.id,
            override=True,
            override_uid=self.manager_user.id,
            reason="Audit test",
        )
        self.env["pos.order"]._process_order(order_data, False)

        overrides = self.env["pos.order.line"].search([
            ("is_negative_override", "=", True),
            ("override_reason", "=", "Audit test"),
        ])
        self.assertTrue(len(overrides) >= 1)
        session.action_pos_session_closing_control()

    def test_concurrent_orders_second_blocked(self):
        """Two sessions selling last unit — second is blocked server-side."""
        self._set_stock(self.product_a, 1)
        session1 = self.env["pos.session"].create({"config_id": self.config.id})
        order_data1 = self._make_order_data(self.product_a, 1, session1.id)
        order_data1["data"]["uid"] = "concurrent-001"
        order_data1["data"]["name"] = "Order concurrent-001"
        self.env["pos.order"]._process_order(order_data1, False)

        session2 = self.env["pos.session"].create({"config_id": self.config.id})
        order_data2 = self._make_order_data(self.product_a, 1, session2.id)
        order_data2["data"]["uid"] = "concurrent-002"
        order_data2["data"]["name"] = "Order concurrent-002"
        with self.assertRaises(UserError):
            self.env["pos.order"]._process_order(order_data2, False)
        session1.action_pos_session_closing_control()
        session2.action_pos_session_closing_control()
