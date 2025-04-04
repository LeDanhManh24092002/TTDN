# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _cart_find_product_line(self, product_id=None, line_id=None, **kwargs):
        self.ensure_one()
        lines = super(SaleOrder, self)._cart_find_product_line(product_id, line_id, **kwargs)
        if line_id:
            return lines
        domain = [('id', 'in', lines.ids)]
        if self.env.context.get("event_ticket_id"):
            domain.append(('event_ticket_id', '=', self.env.context.get("event_ticket_id")))
        return self.env['sale.order.line'].sudo().search(domain)

    def _website_product_id_change(self, order_id, product_id, qty=0, **kwargs):
        order = self.env['sale.order'].sudo().browse(order_id)
        if self._context.get('pricelist') != order.pricelist_id.id:
            self = self.with_context(pricelist=order.pricelist_id.id)

        values = super(SaleOrder, self)._website_product_id_change(order_id, product_id, qty=qty, **kwargs)
        event_ticket_id = None
        if self.env.context.get("event_ticket_id"):
            event_ticket_id = self.env.context.get("event_ticket_id")
        else:
            product = self.env['product.product'].browse(product_id)
            if product.event_ticket_ids:
                event_ticket_id = product.event_ticket_ids[0].id

        if event_ticket_id:
            ticket = self.env['event.event.ticket'].browse(event_ticket_id)
            if product_id != ticket.product_id.id:
                raise UserError(_("The ticket doesn't match with this product."))

            values['product_id'] = ticket.product_id.id
            values['event_id'] = ticket.event_id.id
            values['event_ticket_id'] = ticket.id
            discount = 0
            ticket_currency = ticket.product_id.currency_id
            pricelist_currency = order.pricelist_id.currency_id
            price_reduce = ticket.price_reduce
            if ticket_currency != pricelist_currency:
                price_reduce = ticket_currency._convert(
                    price_reduce,
                    pricelist_currency,
                    order.company_id,
                    order.date_order or fields.Datetime.now()
                )
            if order.pricelist_id.discount_policy == 'without_discount':
                price = ticket.price
                if price != 0:
                    if ticket_currency != pricelist_currency:
                        price = ticket_currency._convert(
                            price,
                            pricelist_currency,
                            order.company_id,
                            order.date_order or fields.Datetime.now()
                        )
                    discount = (price - price_reduce) / price * 100
                    price_unit = price
                    if discount < 0:
                        discount = 0
                        price_unit = price_reduce
                else:
                    price_unit = price_reduce
            else:
                price_unit = price_reduce

            if order.pricelist_id and order.partner_id:
                order_line = order._cart_find_product_line(ticket.product_id.id)
                if order_line:
                    price_unit = self.env['account.tax']._fix_tax_included_price_company(price_unit, ticket.product_id.taxes_id, order_line[0].tax_id, self.company_id)

            values.update(
                discount=discount,
                name=ticket._get_ticket_multiline_description(),
                price_unit=price_unit,
            )

        # avoid writing related values that end up locking the product record
        values.pop('event_ok', None)

        return values

    def _cart_update(self, product_id=None, line_id=None, add_qty=0, set_qty=0, **kwargs):
        OrderLine = self.env['sale.order.line']

        try:
            if add_qty:
                add_qty = float(add_qty)
        except ValueError:
            add_qty = 1
        try:
            if set_qty:
                set_qty = float(set_qty)
        except ValueError:
            set_qty = 0

        if line_id:
            line = OrderLine.browse(line_id)
            ticket = line.event_ticket_id
            old_qty = int(line.product_uom_qty)
            if ticket.id:
                self = self.with_context(event_ticket_id=ticket.id, fixed_price=1)
        else:
            ticket_domain = [('product_id', '=', product_id)]
            if self.env.context.get("event_ticket_id"):
                ticket_domain = expression.AND([ticket_domain, [('id', '=', self.env.context['event_ticket_id'])]])
            ticket = self.env['event.event.ticket'].search(ticket_domain, limit=1)
            old_qty = 0
        new_qty = set_qty if set_qty else (add_qty or 0 + old_qty)

        # case: buying tickets for a sold out ticket
        values = {}
        increased_quantity = new_qty > old_qty
        if ticket and ticket.seats_limited and ticket.seats_available <= 0 and increased_quantity:
            values['warning'] = _('Sorry, The %(ticket)s tickets for the %(event)s event are sold out.') % {
                'ticket': ticket.name,
                'event': ticket.event_id.name}
            new_qty, set_qty, add_qty = 0, 0, -old_qty
        # case: buying tickets, too much attendees
        elif ticket and ticket.seats_limited and new_qty > ticket.seats_available and increased_quantity:
            values['warning'] = _('Sorry, only %(remaining_seats)d seats are still available for the %(ticket)s ticket for the %(event)s event.') % {
                'remaining_seats': ticket.seats_available,
                'ticket': ticket.name,
                'event': ticket.event_id.name}
            new_qty, set_qty, add_qty = ticket.seats_available, ticket.seats_available, 0
        values.update(super(SaleOrder, self)._cart_update(product_id, line_id, add_qty, set_qty, **kwargs))

        # removing attendees
        if ticket and new_qty < old_qty:
            attendees = self.env['event.registration'].search([
                ('state', '!=', 'cancel'),
                ('sale_order_id', 'in', self.ids),  # To avoid break on multi record set
                ('event_ticket_id', '=', ticket.id),
            ], offset=new_qty, limit=(old_qty - new_qty), order='create_date asc')
            attendees.action_cancel()
        # adding attendees
        elif ticket and new_qty > old_qty:
            # do not do anything, attendees will be created at SO confirmation if not given previously
            pass
        return values


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends('product_id.display_name', 'event_ticket_id.display_name')
    def _compute_name_short(self):
        """ If the sale order line concerns a ticket, we don't want the product name, but the ticket name instead.
        """
        super(SaleOrderLine, self)._compute_name_short()

        for record in self:
            if record.event_ticket_id:
                record.name_short = record.event_ticket_id.display_name
