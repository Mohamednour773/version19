# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class PettyCashSettlementWizard(models.TransientModel):
    _name = 'petty.cash.settlement.wizard'
    _description = 'Quick Settlement Wizard'

    custody_id = fields.Many2one('hr.petty.cash', string='Custody', required=True)
    settlement_date = fields.Date(string='Settlement Date', default=fields.Date.today, required=True)
    notes = fields.Text(string='Notes')

    def action_create_and_open(self):
        self.ensure_one()
        if self.custody_id.state != 'paid':
            raise UserError(_('Custody must be in Paid state to create a settlement.'))
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': self.custody_id.id,
            'settlement_date': self.settlement_date,
            'company_id': self.custody_id.company_id.id,
            'notes': self.notes,
        })
        self.custody_id.write({'state': 'settlement_in_progress'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement'),
            'res_model': 'petty.cash.settlement',
            'res_id': settlement.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'current',
        }
