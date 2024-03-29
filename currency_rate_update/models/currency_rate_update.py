# © 2009-2016 Camptocamp
# © 2010 Akretion
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from datetime import datetime, time
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
import ipdb

from ..services.currency_getter_interface import CurrencyGetterType


_logger = logging.getLogger(__name__)

_intervalTypes = {
    'days': lambda interval: relativedelta(days=interval),
    'weeks': lambda interval: relativedelta(days=7*interval),
    'months': lambda interval: relativedelta(months=interval),
}


class CurrencyRateUpdateService(models.Model):
    """Class keep services and currencies that
    have to be updated"""
    _name = "currency.rate.update.service"
    _inherit = ['mail.thread']
    _description = "Currency Rate Update"
    _rec_name = "service"


    @api.constrains('max_delta_days')
    def _check_max_delta_days(self):
        for srv in self:
            if srv.max_delta_days < 0:
                raise ValidationError(_(
                    'Max delta days must be >= 0'))


    @api.constrains('interval_number')
    def _check_interval_number(self):
        for srv in self:
            if srv.interval_number < 0:
                raise ValidationError(_('Interval number must be >= 0'))


    def write(self, vals):
        if 'interval_number' in vals and vals['interval_number'] == 0:
            for service in self:
                msg = '%s Service deactivated. Currencies will no longer ' \
                      'be updated.' % (fields.Datetime.now())
                service.message_post(body=msg,
                                     message_type='comment',
                                     subtype='mt_comment')
        return super(CurrencyRateUpdateService, self).write(vals)

    @api.onchange('service')
    def _onchange_service(self):
        currency_list = False
        res = {'domain': {
            'currency_to_update': "[('id', '=', False)]",
        }}
        if self.service:
            getter = CurrencyGetterType.get(self.service)
            currency_list = getter.supported_currency_array
            currencies = self.env['res.currency'].search([('name', 'in', currency_list)])
            currency_list = [(6, 0, currencies.ids)]
            res['domain']['currency_to_update'] = "[('id', 'in', %s)]" % currencies.ids
        self.currency_list = currency_list
        return res

    def _selection_service(self, *a, **k):
        res = [(x.code, x.name) for x in CurrencyGetterType.getters.values()]
        return res

    # List of webservicies the value sould be a class name
    service = fields.Selection(
        _selection_service,
        string="Webservice to use",
        required=True)
    # List of currencies available on webservice
    currency_list = fields.Many2many('res.currency',
                                     'res_currency_update_avail_rel',
                                     'service_id',
                                     'currency_id',
                                     string='Currencies available')
    # I can't just put readonly=True in the field above because I need
    # it as r+w for the on_change to work
    currency_list_readonly = fields.Many2many(
        related='currency_list', readonly=True)
    # List of currency to update
    currency_to_update = fields.Many2many('res.currency',
                                          'res_currency_auto_update_rel',
                                          'service_id',
                                          'currency_id',
                                          string='Currencies to update with '
                                                 'this service')
    # Link with company
    company_id = fields.Many2one(
        'res.company', 'Company', required=True,
        default=lambda self: self.env['res.company']._company_default_get(
            'currency.rate.update.service'))
    max_delta_days = fields.Integer(
        string='Max delta days', default=4, required=True,
        help="If the time delta between the rate date given by the "
             "webservice and the current date exceeds this value, "
             "then the currency rate is not updated in Odoo.")
    interval_type = fields.Selection([
        ('days', 'Day(s)'),
        ('weeks', 'Week(s)'),
        ('months', 'Month(s)')],
        string='Currency update frequency',
        default='days')
    interval_number = fields.Integer(string='Frequency', default=1)
    next_run = fields.Date(string='Next run on', default=fields.Date.today())

    _sql_constraints = [('curr_service_unique',
                         'unique (service, company_id)',
                         _('You can use a service only one time per '
                           'company !'))]


    def refresh_currency(self):
        """Refresh the currencies rates !!for all companies now"""
        rate_obj = self.env['res.currency.rate']
        for srv in self:
            _logger.info(
                'Starting to refresh currencies with service %s (company: %s)',
                srv.service, srv.company_id.name)
            company = srv.company_id
            # The multi company currency can be set or no so we handle
            # The two case
            if company.auto_currency_up:
                main_currency = company.currency_id
                # No need to test if main_currency exists, because it is a
                # required field
                if float_compare(
                        main_currency.with_context(company_id=company.id).rate,
                        1, precision_rounding=main_currency.rounding):
                    raise UserError(_(
                        "In company '%s', the rate of the main currency (%s) "
                        "must be 1.00 (current rate: %s).") % (
                                        company.name,
                                        main_currency.name,
                                        main_currency.rate))
                try:
                    # We initalize the class that will handle the request
                    # and return a dict of rate
                    getter = CurrencyGetterType.get(srv.service)
                    curr_to_fetch = [x.name for x in srv.currency_to_update]
                    res, log_info = getter.get_updated_currency(
                        curr_to_fetch,
                        main_currency.name,
                        srv.max_delta_days
                    )
                    rate_name = fields.Datetime.to_string(datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0))
                    for curr in srv.currency_to_update:
                        if curr == main_currency:
                            continue
                        rates = rate_obj.search([
                            ('currency_id', '=', curr.id),
                            ('company_id', '=', company.id),
                            ('name', '=', rate_name)])
                        if not rates:
                            rate = res[curr.name]
                            # Used in currency_rate_inverted module. We do
                            # not want to add a glue module for the currency
                            # update.
                            if 'rate_inverted' in self.env['res.currency']._fields:
                                if curr.with_context(force_company=company.id).rate_inverted:
                                    rate = 1/rate
                            vals = {
                                'currency_id': curr.id,
                                'rate': rate,
                                'name': rate_name,
                                'company_id': company.id,
                            }
                            rate_obj.create(vals)
                            _logger.info(
                                'Updated currency %s via service %s '
                                'in company %s',
                                curr.name, srv.service, company.name)

                    # Show the most recent note at the top
                    msg = '%s <br/>%s currency updated.' % (
                        log_info or '',
                        fields.Datetime.to_string(datetime.today())
                    )
                    srv.message_post(body=msg)
                except Exception as exc:
                    error_msg = '%s ERROR: %s' % (
                        fields.Datetime.to_string(datetime.today()),
                        repr(exc)
                    )
                    _logger.error(repr(exc))
                    srv.message_post(body=error_msg,
                                     message_type='comment',
                                     subtype='mt_comment')
                if self._context.get('cron'):
                    midnight = time(0, 0)
                    next_run = (datetime.combine(
                        fields.Date.from_string(srv.next_run),
                        midnight) +
                                _intervalTypes[str(srv.interval_type)]
                                (srv.interval_number)).date()
                    srv.next_run = next_run
        return True


    def run_currency_update(self):
        # Update currency at the given frequence
        services = self.search([('next_run', '=', fields.Date.today())])
        services.with_context(cron=True).refresh_currency()

    @api.model
    def _run_currency_update(self):
        _logger.info('Starting the currency rate update cron')
        print('Starting the currency rate update cron')
        self.run_currency_update()
        _logger.info('End of the currency rate update cron')
        print('End of the currency rate update cron')
