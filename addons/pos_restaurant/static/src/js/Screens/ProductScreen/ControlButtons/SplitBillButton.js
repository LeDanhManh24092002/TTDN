odoo.define('pos_restaurant.SplitBillButton', function(require) {
    'use strict';

    const PosComponent = require('point_of_sale.PosComponent');
    const ProductScreen = require('point_of_sale.ProductScreen');
    const { useListener } = require('web.custom_hooks');
    const Registries = require('point_of_sale.Registries');

    class SplitBillButton extends PosComponent {
        constructor() {
            super(...arguments);
            useListener('click', this.onClick);
        }
        async onClick() {
            const order = this.env.pos.get_order();
            if (order.get_orderlines().length > 0) {
                this.trigger('close-popup');
                this.showScreen('SplitBillScreen');
            }
        }
    }
    SplitBillButton.template = 'SplitBillButton';

    ProductScreen.addControlButton({
        component: SplitBillButton,
        condition: function() {
            return this.env.pos.config.iface_splitbill;
        },
    });

    Registries.Component.add(SplitBillButton);

    return SplitBillButton;
});
