# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class ClubReportSessionUtilization(models.Model):
    """
    SQL-backed read-only view for session utilization reporting.
    Allows pivot, list, and graph analysis without heavy ORM queries.
    """
    _name = 'club.report.session.utilization'
    _description = 'Session Utilization Report'
    _auto = False
    _rec_name = 'session_name'
    _order = 'date desc'

    session_name = fields.Char(string='Session', readonly=True)
    branch_id = fields.Many2one('club.branch', string='Branch', readonly=True)
    trainer_id = fields.Many2one('club.trainer', string='Trainer', readonly=True)
    class_id = fields.Many2one('club.class', string='Class', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    class_type = fields.Selection([
        ('group', 'Group'),
        ('private', 'Private'),
    ], string='Type', readonly=True)
    specialization = fields.Char(string='Sport', readonly=True)
    max_capacity = fields.Integer(string='Capacity', readonly=True)
    enrolled_count = fields.Integer(string='Enrolled', readonly=True)
    attended_count = fields.Integer(string='Attended', readonly=True)
    absent_count = fields.Integer(string='Absent', readonly=True)
    utilization_pct = fields.Float(string='Utilization %', digits=(5, 1), readonly=True)
    state = fields.Char(string='Status', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW club_report_session_utilization AS (
                SELECT
                    s.id                                        AS id,
                    s.name                                      AS session_name,
                    s.branch_id                                 AS branch_id,
                    s.trainer_id                                AS trainer_id,
                    s.class_id                                  AS class_id,
                    s.date                                      AS date,
                    s.class_type                                AS class_type,
                    s.specialization                            AS specialization,
                    COALESCE(s.max_capacity, 0)                 AS max_capacity,
                    COALESCE(s.enrolled_count, 0)               AS enrolled_count,
                    COALESCE(s.attended_count, 0)               AS attended_count,
                    COALESCE(
                        s.enrolled_count - s.attended_count, 0
                    )                                           AS absent_count,
                    CASE
                        WHEN COALESCE(s.max_capacity, 0) > 0
                        THEN ROUND(
                            (COALESCE(s.attended_count, 0)::numeric
                             / s.max_capacity) * 100, 1
                        )
                        ELSE 0
                    END                                         AS utilization_pct,
                    s.state                                     AS state
                FROM club_session s
                WHERE s.state != 'cancelled'
            )
        """)


class ClubReportTrainerRevenue(models.Model):
    """
    Trainer revenue & commission summary report.
    """
    _name = 'club.report.trainer.revenue'
    _description = 'Trainer Revenue Report'
    _auto = False
    _rec_name = 'trainer_id'
    _order = 'date desc'

    trainer_id = fields.Many2one('club.trainer', string='Trainer', readonly=True)
    branch_id = fields.Many2one('club.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    session_id = fields.Many2one('club.session', string='Session', readonly=True)
    attended_count = fields.Integer(string='Attended', readonly=True)
    session_revenue = fields.Float(string='Session Revenue', digits=(16, 2), readonly=True)
    commission_pct = fields.Float(string='Commission %', digits=(5, 2), readonly=True)
    commission_amount = fields.Float(string='Commission', digits=(16, 2), readonly=True)
    state = fields.Char(string='Status', readonly=True)
    specialization = fields.Char(string='Sport', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW club_report_trainer_revenue AS (
                SELECT
                    tc.id                               AS id,
                    tc.trainer_id                       AS trainer_id,
                    tc.branch_id                        AS branch_id,
                    tc.date                             AS date,
                    tc.session_id                       AS session_id,
                    tc.attended_count                   AS attended_count,
                    tc.session_revenue                  AS session_revenue,
                    tc.commission_pct                   AS commission_pct,
                    tc.amount                           AS commission_amount,
                    tc.state                            AS state,
                    ct.specialization                   AS specialization
                FROM club_trainer_commission tc
                LEFT JOIN club_trainer ct ON ct.id = tc.trainer_id
            )
        """)


class ClubReportCash(models.Model):
    """
    Cash / revenue report grouped by branch and payment method.
    Shows both membership payments and rental bookings.
    """
    _name = 'club.report.cash'
    _description = 'Cash & Revenue Report'
    _auto = False
    _rec_name = 'reference'
    _order = 'date desc'

    reference = fields.Char(string='Reference', readonly=True)
    source = fields.Selection([
        ('membership', 'Membership'),
        ('rental', 'Rental'),
    ], string='Source', readonly=True)
    branch_id = fields.Many2one('club.branch', string='Branch', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    amount = fields.Float(string='Amount', digits=(16, 2), readonly=True)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('transfer', 'Bank Transfer'),
    ], string='Payment Method', readonly=True)
    payment_state = fields.Char(string='Payment Status', readonly=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW club_report_cash AS (
                -- Memberships
                SELECT
                    ROW_NUMBER() OVER ()                AS id,
                    m.name                              AS reference,
                    'membership'                        AS source,
                    m.branch_id                         AS branch_id,
                    m.partner_id                        AS partner_id,
                    m.date_start                        AS date,
                    m.price                             AS amount,
                    m.payment_method                    AS payment_method,
                    COALESCE(am.payment_state, 'not_paid') AS payment_state,
                    m.invoice_id                        AS invoice_id
                FROM club_membership m
                LEFT JOIN account_move am ON am.id = m.invoice_id
                WHERE m.state NOT IN ('cancelled', 'draft')

                UNION ALL

                -- Rentals
                SELECT
                    ROW_NUMBER() OVER ()                AS id,
                    r.name                              AS reference,
                    'rental'                            AS source,
                    r.branch_id                         AS branch_id,
                    r.partner_id                        AS partner_id,
                    r.date_start::date                  AS date,
                    r.total_price                       AS amount,
                    r.payment_method                    AS payment_method,
                    COALESCE(am.payment_state, 'not_paid') AS payment_state,
                    r.invoice_id                        AS invoice_id
                FROM club_rental r
                LEFT JOIN account_move am ON am.id = r.invoice_id
                WHERE r.state NOT IN ('cancelled', 'draft')
            )
        """)
