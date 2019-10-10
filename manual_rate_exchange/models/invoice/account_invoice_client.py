# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError
import logging
import ipdb



_logger = logging.getLogger(__name__)



class AccountInvoiceC(models.Model):
    
    _inherit = 'account.move'


    check_rate = fields.Boolean(help='Cantidad de unidades de la moneda base con respecto a la moneda extranjera', string='Tasa de cambio manual')
    rate_exchange = fields.Float(help='Cantidad de unidades de la moneda base con respecto a la moneda extranjera', string='Tasa de cambio')

    @api.onchange('check_rate')
    def line_ids_invoice(self):
        if self.check_rate == False:
            for data in self.invoice_line_ids:
                data.local_currency_price = None
        else:
            check_rate = self.check_rate
            rate_exchange = self.rate_exchange
            ctx = self.env.context.copy()
            ctx.update({'value_check_rate': check_rate })
            ctx.update({'value_rate_exchange': rate_exchange })
            self.env.context = ctx
            for data in self.invoice_line_ids:
                data.local_currency_price = data.quantity*data.price_unit * self.rate_exchange

    @api.onchange('rate_exchange')
    def update_local_currency(self):
        for data in self.invoice_line_ids:
            data.local_currency_price=data.quantity*data.price_unit * self.rate_exchange


    def action_post(self):
        company = self.env['res.company'].browse(1)
        rates = self.currency_id._get_rates(company, self.date)
        if self.mapped('line_ids.payment_id') and any(post_at == 'bank_rec' for post_at in self.mapped('journal_id.post_at')):
            raise UserError(_("A payment journal entry generated in a journal configured to post entries only when payments are reconciled with a bank statement cannot be manually posted. Those will be posted automatically after performing the bank reconciliation."))
        return self.post()











