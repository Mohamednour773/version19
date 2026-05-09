# -*- coding: utf-8 -*-
import logging

from odoo import models


_logger = logging.getLogger(__name__)


class ClubReportDashboardExtension(models.TransientModel):
    _inherit = 'club.report.dashboard'

    def get_data(self):
        data = super().get_data()
        data.setdefault('kpis', {})
        data['kpis'].setdefault('overdue_count', 0)
        data['kpis'].setdefault('overdue_amount', 0.0)
        try:
            overdue_model = self.env['club.report.overdue']
            if overdue_model.check_access_rights('read', raise_exception=False):
                overdue = overdue_model.search([])
                data['kpis']['overdue_count'] = len(overdue)
                data['kpis']['overdue_amount'] = round(sum(overdue.mapped('amount_residual')), 2)
        except Exception:
            _logger.exception('Dashboard overdue extension failed')
        return data
