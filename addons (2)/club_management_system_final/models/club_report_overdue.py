# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ClubReportOverdue(models.Model):
    _name = 'club.report.overdue'
    _description = 'Overdue Invoices Report'
    _auto = False
    _rec_name = 'reference'
    _order = 'days_overdue desc, due_date asc'

    reference = fields.Char(string='Reference', readonly=True)
    branch_id = fields.Many2one('club.branch', string='Branch', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    source = fields.Selection([
        ('membership', 'Membership'),
        ('rental', 'Rental'),
    ], string='Source', readonly=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    due_date = fields.Date(string='Due Date', readonly=True)
    amount_total = fields.Float(string='Invoice Total', digits=(16, 2), readonly=True)
    amount_residual = fields.Float(string='Amount Due', digits=(16, 2), readonly=True)
    days_overdue = fields.Integer(string='Days Overdue', readonly=True)
    payment_state = fields.Char(string='Payment Status', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW club_report_overdue AS (
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY due_date ASC NULLS LAST, reference
                    ) AS id,
                    reference,
                    branch_id,
                    partner_id,
                    source,
                    invoice_id,
                    due_date,
                    amount_total,
                    amount_residual,
                    GREATEST((CURRENT_DATE - due_date), 0) AS days_overdue,
                    payment_state
                FROM (
                    SELECT
                        m.name AS reference,
                        m.branch_id AS branch_id,
                        m.partner_id AS partner_id,
                        'membership' AS source,
                        am.id AS invoice_id,
                        COALESCE(am.invoice_date_due, am.invoice_date) AS due_date,
                        am.amount_total AS amount_total,
                        am.amount_residual AS amount_residual,
                        am.payment_state AS payment_state
                    FROM club_membership m
                    JOIN account_move am ON am.id = m.invoice_id
                    WHERE am.move_type = 'out_invoice'
                      AND am.state = 'posted'
                      AND am.payment_state IN ('not_paid', 'partial')
                    UNION ALL
                    SELECT
                        r.name AS reference,
                        r.branch_id AS branch_id,
                        r.partner_id AS partner_id,
                        'rental' AS source,
                        am.id AS invoice_id,
                        COALESCE(am.invoice_date_due, am.invoice_date) AS due_date,
                        am.amount_total AS amount_total,
                        am.amount_residual AS amount_residual,
                        am.payment_state AS payment_state
                    FROM club_rental r
                    JOIN account_move am ON am.id = r.invoice_id
                    WHERE am.move_type = 'out_invoice'
                      AND am.state = 'posted'
                      AND am.payment_state IN ('not_paid', 'partial')
                ) overdue
                WHERE due_date < CURRENT_DATE
            )
        """)
