from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestIonicProjectDashboard(TransactionCase):
    def test_dashboard_data_returns_kpis_and_sectors(self):
        project = self.env["project.project"].create({
            "name": "Dashboard Test Project",
            "is_ionic_project": True,
        })
        self.env["ionic.project.sector"].create({
            "name": "Dashboard Sector",
            "code": "R",
            "project_id": project.id,
            "target_qty": 10.0,
            "uom_id": self.env.ref("uom.product_uom_unit").id,
        })
        data = self.env["ionic.project.dashboard"].get_dashboard_data(project.id)
        self.assertEqual(data["kpis"]["active_projects"], 1)
        self.assertEqual(len(data["sectors"]), 1)
