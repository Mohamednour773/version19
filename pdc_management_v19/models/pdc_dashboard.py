from datetime import timedelta

from babel.dates import format_date as _babel_format_date

from odoo import api, fields, models


class PDCDashboard(models.TransientModel):
    _name = 'pdc.dashboard'
    _description = 'PDC Dashboard'

    # ── Company / Currency ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
    )
    company_name = fields.Char(
        related='company_id.name',
        readonly=True,
        string='Company',
    )

    # ── UI state flags ────────────────────────────────────────────────────────
    has_any_checks = fields.Boolean(
        compute='_compute_kpis',
        string='Has Any Checks',
    )
    has_chart_data = fields.Boolean(
        compute='_compute_charts',
        string='Has Chart Data',
    )

    # ── KPI Card 1: Under Collection ─────────────────────────────────────────
    total_under_collection = fields.Monetary(
        compute='_compute_kpis',
        string='Total Under Collection',
        currency_field='currency_id',
    )
    under_collection_count = fields.Integer(compute='_compute_kpis')

    # ── KPI Card 2: Due This Week ─────────────────────────────────────────────
    due_this_week_amount = fields.Monetary(
        compute='_compute_kpis',
        string='Due This Week',
        currency_field='currency_id',
    )
    due_this_week_count = fields.Integer(compute='_compute_kpis')

    # ── KPI Card 3: Bounced This Month ────────────────────────────────────────
    bounced_this_month_amount = fields.Monetary(
        compute='_compute_kpis',
        string='Bounced This Month',
        currency_field='currency_id',
    )
    bounced_this_month_count = fields.Integer(compute='_compute_kpis')

    # ── KPI Card 4: Cleared This Month ────────────────────────────────────────
    cleared_this_month_amount = fields.Monetary(
        compute='_compute_kpis',
        string='Cleared This Month',
        currency_field='currency_id',
    )
    cleared_this_month_count = fields.Integer(compute='_compute_kpis')

    # ── Cash Flow Forecast ────────────────────────────────────────────────────
    cash_inflow_30d = fields.Monetary(
        compute='_compute_kpis',
        string='Expected Inflow (30 days)',
        currency_field='currency_id',
    )
    cash_inflow_60d = fields.Monetary(
        compute='_compute_kpis',
        string='Expected Inflow (60 days)',
        currency_field='currency_id',
    )
    cash_inflow_90d = fields.Monetary(
        compute='_compute_kpis',
        string='Expected Inflow (90 days)',
        currency_field='currency_id',
    )
    cash_outflow_30d = fields.Monetary(
        compute='_compute_kpis',
        string='Expected Outflow (30 days)',
        currency_field='currency_id',
    )

    # ── Quality Metrics ───────────────────────────────────────────────────────
    bounce_rate_percent = fields.Float(
        compute='_compute_kpis',
        string='Bounce Rate %',
        digits=(5, 1),
    )
    overdue_count = fields.Integer(
        compute='_compute_kpis',
        string='Overdue Checks',
    )

    # ── Chart Data (JSON) ─────────────────────────────────────────────────────
    state_distribution_data = fields.Json(
        compute='_compute_charts',
        string='Checks by State',
    )
    top_partners_data = fields.Json(
        compute='_compute_charts',
        string='Top 5 Partners',
    )
    monthly_cash_flow_data = fields.Json(
        compute='_compute_charts',
        string='Monthly Cash Flow',
    )
    bounce_reasons_data = fields.Json(
        compute='_compute_charts',
        string='Bounce Reasons',
    )

    # =========================================================================
    # DISPLAY NAME
    # =========================================================================

    @api.depends('company_id')
    def _compute_display_name(self):
        """Always show 'PDC Dashboard' in the breadcrumb, never 'pdc.dashboard,N'."""
        for record in self:
            record.display_name = 'PDC Dashboard'

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _to_company_currency(self, checks, company, rate_date):
        """Sum check amounts, converting each to company currency at *rate_date*.

        This is Option A conversion: uses today's rate for all checks.
        Suitable for dashboard display; not for bookkeeping entries.

        :param checks:    pdc.check recordset
        :param company:   res.company record
        :param rate_date: date for FX look-up (pass today for dashboard)
        :returns:         float — total in company currency
        """
        if not checks:
            return 0.0
        co_currency = company.currency_id
        total = 0.0
        for check in checks:
            if check.currency_id == co_currency:
                total += check.amount
            else:
                total += check.currency_id._convert(
                    check.amount, co_currency, company, rate_date,
                )
        return total

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('company_id')
    def _compute_kpis(self):
        """Compute all KPI values from pdc.check.
        All monetary amounts are converted to company currency at today's rate.
        """
        Check = self.env['pdc.check']
        today = fields.Date.today()

        for record in self:
            company = record.company_id

            if not company:
                # Guard: new record before default is applied
                record.has_any_checks = False
                record.total_under_collection = 0.0
                record.under_collection_count = 0
                record.due_this_week_amount = 0.0
                record.due_this_week_count = 0
                record.bounced_this_month_amount = 0.0
                record.bounced_this_month_count = 0
                record.cleared_this_month_amount = 0.0
                record.cleared_this_month_count = 0
                record.cash_inflow_30d = 0.0
                record.cash_inflow_60d = 0.0
                record.cash_inflow_90d = 0.0
                record.cash_outflow_30d = 0.0
                record.bounce_rate_percent = 0.0
                record.overdue_count = 0
                continue

            def _sum(recs):
                return self._to_company_currency(recs, company, today)

            domain = [('company_id', '=', company.id)]
            month_start = today.replace(day=1)

            # ── Empty state flag ──────────────────────────────────────────────
            record.has_any_checks = bool(Check.search_count(domain))

            # ── Card 1: Under Collection ──────────────────────────────────────
            under_coll = Check.search(domain + [('state', '=', 'under_collection')])
            record.total_under_collection = _sum(under_coll)
            record.under_collection_count = len(under_coll)

            # ── Card 2: Due This Week ─────────────────────────────────────────
            week_end = today + timedelta(days=7)
            due_week = Check.search(domain + [
                ('state', 'in', ['registered', 'under_collection']),
                ('due_date', '>=', today),
                ('due_date', '<=', week_end),
            ])
            record.due_this_week_amount = _sum(due_week)
            record.due_this_week_count = len(due_week)

            # ── Card 3: Bounced This Month ────────────────────────────────────
            bounced = Check.search(domain + [
                ('state', '=', 'bounced'),
                ('bounce_date', '>=', month_start),
            ])
            record.bounced_this_month_amount = _sum(bounced)
            record.bounced_this_month_count = len(bounced)

            # ── Card 4: Cleared This Month ────────────────────────────────────
            cleared = Check.search(domain + [
                ('state', '=', 'cleared'),
                ('clear_date', '>=', month_start),
            ])
            record.cleared_this_month_amount = _sum(cleared)
            record.cleared_this_month_count = len(cleared)

            # ── Cash Inflow Forecast (received, not yet due) ──────────────────
            inflow_base = domain + [
                ('check_type', '=', 'received'),
                ('state', 'in', ['registered', 'under_collection']),
                ('due_date', '>=', today),
            ]
            for days, attr in [
                (30, 'cash_inflow_30d'),
                (60, 'cash_inflow_60d'),
                (90, 'cash_inflow_90d'),
            ]:
                setattr(record, attr, _sum(Check.search(
                    inflow_base + [('due_date', '<=', today + timedelta(days=days))]
                )))

            # ── Cash Outflow Forecast (issued, due in 30d) ────────────────────
            # Include 'registered' so treasury managers see ALL committed
            # outflows, not only physically-delivered cheques.
            record.cash_outflow_30d = _sum(Check.search(domain + [
                ('check_type', '=', 'issued'),
                ('state', 'in', ['registered', 'printed', 'delivered']),
                ('due_date', '>=', today),
                ('due_date', '<=', today + timedelta(days=30)),
            ]))

            # ── Bounce Rate (last 12 months) ──────────────────────────────────
            year_ago = today - timedelta(days=365)
            total_completed = Check.search_count(domain + [
                ('state', 'in', ['cleared', 'bounced', 'paid']),
                ('create_date', '>=', year_ago),
            ])
            total_bounced = Check.search_count(domain + [
                ('state', '=', 'bounced'),
                ('create_date', '>=', year_ago),
            ])
            record.bounce_rate_percent = (
                (total_bounced / total_completed * 100.0) if total_completed else 0.0
            )

            # ── Overdue Checks ────────────────────────────────────────────────
            record.overdue_count = Check.search_count(domain + [
                ('state', 'in', ['registered', 'under_collection']),
                ('due_date', '<', today),
            ])

    @api.depends('company_id')
    def _compute_charts(self):
        """Build JSON chart data structures for the dashboard."""
        Check = self.env['pdc.check']
        today = fields.Date.today()

        for record in self:
            company = record.company_id

            if not company:
                record.state_distribution_data = {'data': []}
                record.top_partners_data = {'data': []}
                record.monthly_cash_flow_data = {'data': []}
                record.bounce_reasons_data = {'data': []}
                record.has_chart_data = False
                continue

            company_id = company.id
            domain = [('company_id', '=', company_id)]
            co_currency = company.currency_id

            # ── Chart 1: Checks by State ──────────────────────────────────────
            active_states = [
                ('registered',       'Registered'),
                ('under_collection', 'Under Collection'),
                ('cleared',          'Cleared'),
                ('bounced',          'Bounced'),
                ('settled',          'Settled'),
                ('printed',          'Printed'),
                ('delivered',        'Delivered'),
                ('paid',             'Paid'),
                ('cancelled',        'Cancelled'),
                ('returned',         'Returned'),
            ]
            state_data = []
            for state_key, state_label in active_states:
                count = Check.search_count(domain + [('state', '=', state_key)])
                if count > 0:
                    state_data.append({'label': state_label, 'value': count})
            record.state_distribution_data = {'data': state_data}

            # has_chart_data: True when at least one state bucket is non-empty
            record.has_chart_data = bool(state_data)

            # ── Chart 2: Top 5 Partners (FX-safe ORM) ────────────────────────
            outstanding = Check.search(domain + [
                ('state', 'in', ['registered', 'under_collection']),
            ])
            partner_totals = {}
            for check in outstanding:
                pid = check.partner_id.id
                if pid not in partner_totals:
                    partner_totals[pid] = {
                        'name': check.partner_id.name or '',
                        'total': 0.0,
                    }
                if check.currency_id == co_currency:
                    partner_totals[pid]['total'] += check.amount
                else:
                    partner_totals[pid]['total'] += check.currency_id._convert(
                        check.amount, co_currency, company, today,
                    )
            top5 = sorted(
                partner_totals.values(),
                key=lambda x: x['total'],
                reverse=True,
            )[:5]
            record.top_partners_data = {
                'data': [
                    {'label': p['name'], 'value': round(p['total'], 2)}
                    for p in top5
                ]
            }

            # ── Chart 3: Monthly Cash Flow (last 6 months) ────────────────────
            # Use babel for locale-aware month labels so Arabic users see
            # "ديسمبر 2025" instead of the strftime output which can be
            # mis-ordered when the server locale is Arabic.
            user_locale = (self.env.user.lang or 'en_US').replace('-', '_')
            cash_flow = []
            for i in range(5, -1, -1):
                month_offset = today.month - i - 1
                year_val = today.year + (month_offset // 12)
                month_num = (month_offset % 12) + 1
                month_start = today.replace(year=year_val, month=month_num, day=1)
                if month_num == 12:
                    next_month = month_start.replace(year=year_val + 1, month=1, day=1)
                else:
                    next_month = month_start.replace(month=month_num + 1, day=1)

                try:
                    month_label = _babel_format_date(
                        month_start, format='MMM yyyy', locale=user_locale,
                    )
                except Exception:
                    month_label = month_start.strftime('%b %Y')

                inflow_recs = Check.search(domain + [
                    ('check_type', '=', 'received'),
                    ('state', '=', 'cleared'),
                    ('clear_date', '>=', month_start),
                    ('clear_date', '<', next_month),
                ])
                outflow_recs = Check.search(domain + [
                    ('check_type', '=', 'issued'),
                    ('state', '=', 'paid'),
                    ('clear_date', '>=', month_start),
                    ('clear_date', '<', next_month),
                ])
                cash_flow.append({
                    'month':   month_label,
                    'inflow':  round(self._to_company_currency(inflow_recs,  company, today), 2),
                    'outflow': round(self._to_company_currency(outflow_recs, company, today), 2),
                })
            record.monthly_cash_flow_data = {'data': cash_flow}

            # ── Chart 4: Bounce Reasons (last 12 months, count-only) ──────────
            year_ago = today - timedelta(days=365)
            self.env.cr.execute("""
                SELECT pbr.name, COUNT(c.id) AS cnt
                FROM pdc_check c
                JOIN pdc_bounce_reason pbr ON c.bounce_reason_id = pbr.id
                WHERE c.company_id = %s
                  AND c.state = 'bounced'
                  AND c.bounce_date >= %s
                GROUP BY pbr.name
                ORDER BY cnt DESC
                LIMIT 6
            """, (company_id, year_ago))
            bounce_rows = self.env.cr.fetchall()
            record.bounce_reasons_data = {
                'data': [
                    {'label': name, 'value': int(cnt)}
                    for name, cnt in bounce_rows
                ]
            }

    # =========================================================================
    # ACTION METHODS
    # =========================================================================

    @api.model
    def action_open_dashboard(self):
        """Create a fresh transient record and open the dashboard form."""
        record = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'PDC Dashboard',
            'res_model': 'pdc.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
            'view_id': self.env.ref('pdc_management_v19.view_pdc_dashboard').id,
        }

    def action_refresh(self):
        """Refresh dashboard by creating a new transient record with current data."""
        return self.env['pdc.dashboard'].action_open_dashboard()

    def action_register_check(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Check',
            'res_model': 'pdc.check',
            'view_mode': 'form',
            'target': 'current',
        }

    def action_aging_report(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Aging Report',
            'res_model': 'pdc.aging.report.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_overdue(self):
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overdue Checks',
            'res_model': 'pdc.check',
            'view_mode': 'list,form',
            'domain': [
                ('state', 'in', ['registered', 'under_collection']),
                ('due_date', '<', today),
            ],
        }

    def action_view_due_soon(self):
        today = fields.Date.today()
        week_end = today + timedelta(days=7)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Due This Week',
            'res_model': 'pdc.check',
            'view_mode': 'list,form',
            'domain': [
                ('state', 'in', ['registered', 'under_collection']),
                ('due_date', '>=', today),
                ('due_date', '<=', week_end),
            ],
        }

    def action_view_under_collection(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Under Collection',
            'res_model': 'pdc.check',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'under_collection')],
        }

    def action_view_bounced(self):
        month_start = fields.Date.today().replace(day=1)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bounced This Month',
            'res_model': 'pdc.check',
            'view_mode': 'list,form',
            'domain': [
                ('state', '=', 'bounced'),
                ('bounce_date', '>=', month_start),
            ],
        }
