from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ── PDC check O2M (both directions use partner_id as FK) ─────────────────
    pdc_received_check_ids = fields.One2many(
        'pdc.check', 'partner_id',
        domain=[('check_type', 'in', ['received', 'guarantee_received'])],
        string='Received Checks',
    )
    pdc_issued_check_ids = fields.One2many(
        'pdc.check', 'partner_id',
        domain=[('check_type', 'in', ['issued', 'guarantee_issued'])],
        string='Issued Checks',
    )

    # ── Stored statistics ─────────────────────────────────────────────────────
    pdc_received_count = fields.Integer(
        string='Received Checks', compute='_compute_pdc_stats',
        store=True,
    )
    pdc_issued_count = fields.Integer(
        string='Issued Checks', compute='_compute_pdc_stats',
        store=True,
    )
    pdc_total_under_collection = fields.Monetary(
        string='Under Collection Total',
        compute='_compute_pdc_stats', store=True,
        currency_field='currency_id',
    )
    pdc_total_due_soon = fields.Monetary(
        string='Due Soon Total',
        compute='_compute_pdc_stats', store=True,
        currency_field='currency_id',
    )
    pdc_bounced_count = fields.Integer(
        string='Bounced Check Count (Historical)',
        compute='_compute_pdc_stats', store=True,
    )

    # ── Block flag ────────────────────────────────────────────────────────────
    pdc_blocked = fields.Boolean(
        string='PDC Blocked',
        default=False,
        help='Partner is blocked due to excessive bounced checks.',
        tracking=True,
    )
    pdc_bounce_threshold = fields.Integer(
        string='Bounce Block Threshold (Override)',
        default=0,
        help='Partner-specific override for the bounce block threshold. '
             '0 means use company default.',
    )

    # ── Compute ───────────────────────────────────────────────────────────────
    @api.depends(
        'pdc_received_check_ids', 'pdc_received_check_ids.state',
        'pdc_received_check_ids.amount', 'pdc_received_check_ids.due_date',
        'pdc_issued_check_ids', 'pdc_issued_check_ids.state',
        'pdc_issued_check_ids.amount',
    )
    def _compute_pdc_stats(self):
        today = fields.Date.today()
        for partner in self:
            received = partner.pdc_received_check_ids
            issued = partner.pdc_issued_check_ids
            all_checks = received | issued

            partner.pdc_received_count = len(received)
            partner.pdc_issued_count = len(issued)

            under_collection = received.filtered(lambda c: c.state == 'under_collection')
            partner.pdc_total_under_collection = sum(under_collection.mapped('amount'))

            due_soon_threshold = partner.env.company.pdc_due_soon_days or 7
            due_soon = received.filtered(
                lambda c: c.state in ('registered', 'under_collection')
                and c.due_date
                and 0 <= (c.due_date - today).days <= due_soon_threshold
            )
            partner.pdc_total_due_soon = sum(due_soon.mapped('amount'))

            partner.pdc_bounced_count = len(
                all_checks.filtered(lambda c: c.state in ('bounced', 'settled'))
            )

    # ── Auto-block check ──────────────────────────────────────────────────────
    def _check_auto_block(self):
        """Block this partner if unsettled bounces exceed the configured threshold."""
        for partner in self:
            company = partner.env.company
            if not company.pdc_auto_block_partners:
                continue
            threshold = partner.pdc_bounce_threshold or company.pdc_block_threshold
            if not threshold:
                continue
            unsettled_bounces = self.env['pdc.check'].search_count([
                ('partner_id', '=', partner.id),
                ('state', '=', 'bounced'),
                ('company_id', '=', company.id),
            ])
            if unsettled_bounces >= threshold and not partner.pdc_blocked:
                partner.write({'pdc_blocked': True})
                partner.message_post(
                    body=_(
                        'Partner automatically blocked: %d unsettled bounced checks '
                        '(threshold: %d).',
                        unsettled_bounces, threshold,
                    )
                )

    # ── Smart button actions ──────────────────────────────────────────────────
    def action_view_pdc_received(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Received Checks'),
            'res_model': 'pdc.check',
            'view_mode': 'list,form,kanban',
            'domain': [
                ('partner_id', '=', self.id),
                ('check_type', 'in', ['received', 'guarantee_received']),
            ],
            'context': {'default_partner_id': self.id, 'default_check_type': 'received'},
        }

    def action_view_pdc_issued(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Issued Checks'),
            'res_model': 'pdc.check',
            'view_mode': 'list,form,kanban',
            'domain': [
                ('partner_id', '=', self.id),
                ('check_type', 'in', ['issued', 'guarantee_issued']),
            ],
            'context': {'default_partner_id': self.id, 'default_check_type': 'issued'},
        }

    def action_open_pdc_statement(self):
        """Open the Partner Statement wizard pre-populated with this partner."""
        self.ensure_one()
        wizard = self.env['pdc.partner.statement.wizard'].create({
            'partner_ids': [(6, 0, [self.id])],
            'company_id': self.env.company.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('PDC Statement — %s', self.name),
            'res_model': 'pdc.partner.statement.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
