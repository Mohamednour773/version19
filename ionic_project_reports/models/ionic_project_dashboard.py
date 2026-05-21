from datetime import timedelta

from odoo import api, fields, models


class IonicProjectDashboard(models.Model):
    _name = "ionic.project.dashboard"
    _description = "Ionic Project Dashboard"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(default="Ionic Project Dashboard")

    @api.model
    def get_dashboard_data(self, project_id=False):
        Project = self.env["project.project"].sudo()
        Sector = self.env["ionic.project.sector"].sudo()
        Supply = self.env["ionic.supply.permit"].sudo()
        Log = self.env["ionic.site.daily.log"].sudo()
        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=7)

        project_domain = [("is_ionic_project", "=", True)]
        if project_id:
            project_domain.append(("id", "=", project_id))
        projects = Project.search(project_domain)
        sector_domain = [("project_id", "in", projects.ids)] if projects else [("id", "=", False)]
        sectors = Sector.search(sector_domain, limit=12)

        delivered_today = sum(Supply.search([
            ("project_id", "in", projects.ids),
            ("date", "=", today),
            ("state", "in", ["received", "with_discrepancy", "closed"]),
        ]).mapped("line_ids.qty_received"))
        installed_week = sum(Log.search([
            ("project_id", "in", projects.ids),
            ("date", ">=", week_start),
            ("state", "=", "posted"),
        ]).mapped("installed_qty"))
        margins = [sector.margin_percent for sector in sectors if sector.total_revenue]
        return {
            "kpis": {
                "active_projects": len(projects),
                "in_production_sectors": Sector.search_count(sector_domain + [("state", "=", "in_progress")]),
                "delivered_today": delivered_today,
                "installed_this_week": installed_week,
                "avg_margin_percent": sum(margins) / len(margins) if margins else 0.0,
            },
            "sectors": [{
                "id": sector.id,
                "name": sector.display_name,
                "target_qty": sector.target_qty,
                "produced_qty": sector.produced_qty,
                "delivered_qty": sector.delivered_qty,
                "installed_qty": sector.installed_qty,
                "damaged_qty": sector.damaged_qty,
            } for sector in sectors],
        }
