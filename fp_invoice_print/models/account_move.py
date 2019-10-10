# -*- coding: utf-8 -*-

from odoo import models, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_tax_amount_by_group(self):
        self.ensure_one()
        res = {}
        res.setdefault(self.env['account.tax'].search([('name', 'ilike', '%Ventas (10%')]), [0.0, 0.0])
        res.setdefault(self.env['account.tax'].search([('name', 'ilike', '%Ventas (22%')]), [0.0, 0.0])
        res.setdefault(self.env['account.tax'].search([('name', 'ilike', '%Ventas Exentos%')]), [0.0, 0.0])
        for line in self.tax_line:
            res.setdefault(line.tax_code_id, [0.0, 0.0])
            res[line.tax_code_id][0] += line.base
            res[line.tax_code_id][1] += line.amount
        res = sorted(res.items(), key=lambda l: l[0].sequence)
        res = map(lambda l: (l[1][0], l[1][1]), res)
        return res