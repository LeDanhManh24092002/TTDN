# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import Form
from odoo.addons.mrp_subcontracting.tests.common import TestMrpSubcontractingCommon


class TestSubcontractingDropshippingFlows(TestMrpSubcontractingCommon):

    def test_mrp_subcontracting_dropshipping_1(self):
        """ Mark the subcontracted product with the route dropship and add the
        subcontractor as seller. The component has the routes 'MTO', 'Replenish
        on order' and 'Buy'. Also another partner is set as vendor on the comp.
        Create a SO and check that:
        - Delivery between subcontractor and customer for subcontracted product.
        - Delivery for the component to the subcontractor for the specified wh.
        - Po created for the component.
        """
        self.env.ref('stock.route_warehouse0_mto').active = True
        mto_route = self.env['stock.location.route'].search([('name', '=', 'Replenish on Order (MTO)')])
        resupply_route = self.env['stock.location.route'].search([('name', '=', 'Resupply Subcontractor on Order')])
        buy_route = self.env['stock.location.route'].search([('name', '=', 'Buy')])
        dropship_route = self.env['stock.location.route'].search([('name', '=', 'Dropship')])
        self.comp2.write({'route_ids': [(4, buy_route.id), (4, mto_route.id), (4, resupply_route.id)]})
        self.finished.write({'route_ids': [(4, dropship_route.id)]})

        warehouse = self.env['stock.warehouse'].create({
            'name': 'Warehouse For subcontract',
            'code': 'WFS'
        })

        self.env['product.supplierinfo'].create({
            'product_tmpl_id': self.finished.product_tmpl_id.id,
            'name': self.subcontractor_partner1.id
        })

        partner = self.env['res.partner'].create({
            'name': 'Toto'
        })
        self.env['product.supplierinfo'].create({
            'product_tmpl_id': self.comp2.product_tmpl_id.id,
            'name': partner.id
        })

        # Create a receipt picking from the subcontractor
        so_form = Form(self.env['sale.order'])
        so_form.partner_id = partner
        so_form.warehouse_id = warehouse
        with so_form.order_line.new() as line:
            line.product_id = self.finished
            line.product_uom_qty = 1
        so = so_form.save()
        so.action_confirm()

        # Pickings should directly be created
        po = self.env['purchase.order'].search([('origin', 'ilike', so.name)])
        self.assertTrue(po)

        po.button_approve()

        picking_finished = po.picking_ids
        self.assertEqual(len(picking_finished), 1.0)
        self.assertEqual(picking_finished.location_dest_id, partner.property_stock_customer)
        self.assertEqual(picking_finished.location_id, self.subcontractor_partner1.property_stock_supplier)
        self.assertEqual(picking_finished.state, 'assigned')

        picking_delivery = self.env['stock.move'].search([
            ('product_id', '=', self.comp2.id),
            ('location_id', '=', warehouse.lot_stock_id.id),
            ('location_dest_id', '=', self.subcontractor_partner1.property_stock_subcontractor.id),
        ]).picking_id
        self.assertTrue(picking_delivery)
        self.assertEqual(picking_delivery.state, 'waiting')

        po = self.env['purchase.order.line'].search([
            ('product_id', '=', self.comp2.id),
            ('partner_id', '=', partner.id),
        ]).order_id
        self.assertTrue(po)

    def test_mrp_subcontracting_purchase_2(self):
        """Let's consider a subcontracted BOM with 1 component. Tick "Resupply Subcontractor on Order" on the component and set a supplier on it.
        Purchase 1 BOM to the subcontractor. Confirm the purchase and change the purchased quantity to 2.
        Check that 2 components are delivered to the subcontractor
        """
        # Tick "resupply subconractor on order on component"
        self.bom.bom_line_ids = [(5, 0, 0)]
        self.bom.bom_line_ids = [(0, 0, {'product_id': self.comp1.id, 'product_qty': 1})]
        resupply_sub_on_order_route = self.env['stock.location.route'].search([('name', '=', 'Resupply Subcontractor on Order')])
        (self.comp1).write({'route_ids': [(4, resupply_sub_on_order_route.id, None)]})
        # Create a supplier and set it to component
        vendor = self.env['res.partner'].create({'name': 'AAA', 'email': 'from.test@example.com'})
        self.env['product.supplierinfo'].create({
            'name': vendor.id,
            'price': 50,
        })
        self.comp1.write({'seller_ids': [(0, 0, {'name': vendor.id, 'product_code': 'COMP1'})]})
        # Purchase 1 BOM to the subcontractor
        po = Form(self.env['purchase.order'])
        po.partner_id = self.subcontractor_partner1
        with po.order_line.new() as po_line:
            po_line.product_id = self.finished
            po_line.product_qty = 1
            po_line.price_unit = 100
        po = po.save()
        # Confirm the purchase
        po.button_confirm()
        # Check one delivery order with the component has been created for the subcontractor
        mo = self.env['mrp.production'].search([('bom_id', '=', self.bom.id)])
        self.assertEqual(mo.state, 'confirmed')
        # Check that 1 delivery with 1 component for the subcontractor has been created
        picking_delivery = mo.picking_ids
        wh = picking_delivery.picking_type_id.warehouse_id
        origin = picking_delivery.origin
        self.assertEqual(len(picking_delivery), 1)
        self.assertEqual(len(picking_delivery.move_ids_without_package), 1)
        self.assertEqual(picking_delivery.picking_type_id, wh.subcontracting_resupply_type_id)
        self.assertEqual(picking_delivery.partner_id, self.subcontractor_partner1)

        # Change the purchased quantity to 2
        po.order_line.write({'product_qty': 2})
        # Check that two deliveries with 1 component for the subcontractor have been created
        picking_deliveries = self.env['stock.picking'].search([('origin', '=', origin)])
        self.assertEqual(len(picking_deliveries), 2)
        self.assertEqual(picking_deliveries[0].picking_type_id, wh.subcontracting_resupply_type_id)
        self.assertEqual(picking_deliveries[0].partner_id, self.subcontractor_partner1)
        self.assertTrue(picking_deliveries[0].state != 'cancel')
        move1 = picking_deliveries[0].move_ids_without_package
        self.assertEqual(picking_deliveries[1].picking_type_id, wh.subcontracting_resupply_type_id)
        self.assertEqual(picking_deliveries[1].partner_id, self.subcontractor_partner1)
        self.assertTrue(picking_deliveries[1].state != 'cancel')
        move2 = picking_deliveries[1].move_ids_without_package
        self.assertEqual(move1.product_id, self.comp1)
        self.assertEqual(move1.product_uom_qty, 1)
        self.assertEqual(move2.product_id, self.comp1)
        self.assertEqual(move2.product_uom_qty, 1)

    def test_dropshipped_component_and_sub_location(self):
        """
        Suppose:
            - a subcontracted product and a component dropshipped to the subcontractor
            - the location of the subcontractor is a sub-location of the main subcontrating location
        This test ensures that the PO that brings the component to the subcontractor has a correct
        destination address
        """
        subcontract_location = self.env.company.subcontracting_location_id
        sub_location = self.env['stock.location'].create({
            'name': 'Super Location',
            'location_id': subcontract_location.id,
        })

        dropship_subcontractor_route = self.env['stock.location.route'].search([('name', '=', 'Dropship Subcontractor on Order')])
        dropship_subcontractor_route.rule_ids.filtered(lambda rule: rule.location_id == subcontract_location).copy(default={'location_id': sub_location.id})
        dropship_subcontractor_route.rule_ids.filtered(lambda rule: rule.location_src_id == subcontract_location).copy(default={'location_src_id': sub_location.id})

        subcontractor, vendor = self.env['res.partner'].create([
            {'name': 'SuperSubcontractor', 'property_stock_subcontractor': sub_location.id},
            {'name': 'SuperVendor'},
        ])

        p_finished, p_compo = self.env['product.product'].create([{
            'name': 'Finished Product',
            'type': 'product',
            'seller_ids': [(0, 0, {'name': subcontractor.id})],
        }, {
            'name': 'Component',
            'type': 'consu',
            'seller_ids': [(0, 0, {'name': vendor.id})],
            'route_ids': [(6, 0, dropship_subcontractor_route.ids)]
        }])

        self.env['mrp.bom'].create({
            'product_tmpl_id': p_finished.product_tmpl_id.id,
            'product_qty': 1,
            'type': 'subcontract',
            'subcontractor_ids': [(6, 0, subcontractor.ids)],
            'bom_line_ids': [
                (0, 0, {'product_id': p_compo.id, 'product_qty': 1}),
            ],
        })

        subcontract_po = self.env['purchase.order'].create({
            "partner_id": subcontractor.id,
            "order_line": [(0, 0, {
                'product_id': p_finished.id,
                'name': p_finished.name,
                'product_qty': 1.0,
            })],
        })
        subcontract_po.button_confirm()

        dropship_po = self.env['purchase.order'].search([('partner_id', '=', vendor.id)])
        self.assertEqual(dropship_po.dest_address_id, subcontractor)

    def test_po_to_customer(self):
        """
        Create and confirm a PO with a subcontracted move. The picking type of
        the PO is 'Dropship' and the delivery address a customer. Then, process
        a return with the stock location as destination and another return with
        the supplier as destination
        """
        subcontractor, client = self.env['res.partner'].create([
            {'name': 'SuperSubcontractor'},
            {'name': 'SuperClient'},
        ])

        p_finished, p_compo = self.env['product.product'].create([{
            'name': 'Finished Product',
            'type': 'product',
            'seller_ids': [(0, 0, {'name': subcontractor.id})],
        }, {
            'name': 'Component',
            'type': 'consu',
        }])

        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': p_finished.product_tmpl_id.id,
            'product_qty': 1,
            'type': 'subcontract',
            'subcontractor_ids': [(6, 0, subcontractor.ids)],
            'bom_line_ids': [
                (0, 0, {'product_id': p_compo.id, 'product_qty': 1}),
            ],
        })

        dropship_picking_type = self.env['stock.picking.type'].search([
            ('company_id', '=', self.env.company.id),
            ('default_location_src_id.usage', '=', 'supplier'),
            ('default_location_dest_id.usage', '=', 'customer'),
        ], limit=1, order='sequence')

        po = self.env['purchase.order'].create({
            "partner_id": subcontractor.id,
            "picking_type_id": dropship_picking_type.id,
            "dest_address_id": client.id,
            "order_line": [(0, 0, {
                'product_id': p_finished.id,
                'name': p_finished.name,
                'product_qty': 2.0,
            })],
        })
        po.button_confirm()

        mo = self.env['mrp.production'].search([('bom_id', '=', bom.id)])
        self.assertEqual(mo.picking_type_id, self.warehouse.subcontracting_type_id)

        delivery = po.picking_ids
        delivery.move_line_ids.qty_done = 2.0
        delivery.button_validate()

        self.assertEqual(delivery.state, 'done')
        self.assertEqual(mo.state, 'done')
        self.assertEqual(po.order_line.qty_received, 2)

        # return 1 x P_finished to the stock location
        stock_location = self.warehouse.lot_stock_id
        stock_location.return_location = True
        return_form = Form(self.env['stock.return.picking'].with_context(active_ids=delivery.ids, active_id=delivery.id, active_model='stock.picking'))
        with return_form.product_return_moves.edit(0) as line:
            line.quantity = 1.0
        return_form.location_id = stock_location
        return_wizard = return_form.save()
        return_picking_id, _pick_type_id = return_wizard._create_returns()

        delivery_return01 = self.env['stock.picking'].browse(return_picking_id)
        delivery_return01.move_line_ids.qty_done = 1.0
        delivery_return01.button_validate()

        self.assertEqual(delivery_return01.state, 'done')
        self.assertEqual(p_finished.qty_available, 1, 'One product has been returned to the stock location, so it should be available')
        self.assertEqual(po.order_line.qty_received, 2, 'One product has been returned to the stock location, so we should still consider it as received')

        # return 1 x P_finished to the supplier location
        supplier_location = dropship_picking_type.default_location_src_id
        return_form = Form(self.env['stock.return.picking'].with_context(active_ids=delivery.ids, active_id=delivery.id, active_model='stock.picking'))
        with return_form.product_return_moves.edit(0) as line:
            line.quantity = 1.0
        return_form.location_id = supplier_location
        return_wizard = return_form.save()
        return_picking_id, _pick_type_id = return_wizard._create_returns()

        delivery_return02 = self.env['stock.picking'].browse(return_picking_id)
        delivery_return02.move_line_ids.qty_done = 1.0
        delivery_return02.button_validate()

        self.assertEqual(delivery_return02.state, 'done')
        self.assertEqual(po.order_line.qty_received, 1)

    def test_po_to_subcontractor(self):
        """
        Create and confirm a PO with a subcontracted move. The bought product is
        also a component of another subcontracted product. The picking type of
        the PO is 'Dropship' and the delivery address is the other subcontractor
        """
        subcontractor, super_subcontractor = self.env['res.partner'].create([
            {'name': 'Subcontractor'},
            {'name': 'SuperSubcontractor'},
        ])

        super_product, product, component = self.env['product.product'].create([{
            'name': 'Super Product',
            'type': 'product',
            'seller_ids': [(0, 0, {'name': super_subcontractor.id})],
        }, {
            'name': 'Product',
            'type': 'product',
            'seller_ids': [(0, 0, {'name': subcontractor.id})],
        }, {
            'name': 'Component',
            'type': 'consu',
        }])

        _, bom_product = self.env['mrp.bom'].create([{
            'product_tmpl_id': super_product.product_tmpl_id.id,
            'product_qty': 1,
            'type': 'subcontract',
            'subcontractor_ids': [(6, 0, super_subcontractor.ids)],
            'bom_line_ids': [
                (0, 0, {'product_id': product.id, 'product_qty': 1}),
            ],
        }, {
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_qty': 1,
            'type': 'subcontract',
            'subcontractor_ids': [(6, 0, subcontractor.ids)],
            'bom_line_ids': [
                (0, 0, {'product_id': component.id, 'product_qty': 1}),
            ],
        }])

        dropship_picking_type = self.env['stock.picking.type'].search([
            ('company_id', '=', self.env.company.id),
            ('default_location_src_id.usage', '=', 'supplier'),
            ('default_location_dest_id.usage', '=', 'customer'),
        ], limit=1, order='sequence')

        po = self.env['purchase.order'].create({
            "partner_id": subcontractor.id,
            "picking_type_id": dropship_picking_type.id,
            "dest_address_id": super_subcontractor.id,
            "order_line": [(0, 0, {
                'product_id': product.id,
                'name': product.name,
                'product_qty': 1.0,
            })],
        })
        po.button_confirm()

        mo = self.env['mrp.production'].search([('bom_id', '=', bom_product.id)])
        self.assertEqual(mo.picking_type_id, self.warehouse.subcontracting_type_id)

        delivery = po.picking_ids
        self.assertEqual(delivery.location_dest_id, super_subcontractor.property_stock_subcontractor)
        self.assertTrue(delivery.is_dropship)

        delivery.move_line_ids.qty_done = 1.0
        delivery.button_validate()

        self.assertEqual(po.order_line.qty_received, 1.0)
