odoo.define('point_of_sale.ErrorPopup', function(require) {
    'use strict';

    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const Registries = require('point_of_sale.Registries');
    const { _lt } = require('@web/core/l10n/translation');

    // formerly ErrorPopupWidget
    class ErrorPopup extends AbstractAwaitablePopup {
        mounted() {
            this.playSound('error');
        }
    }
    ErrorPopup.template = 'ErrorPopup';
    ErrorPopup.defaultProps = {
        confirmText: _lt('Ok'),
        cancelText: _lt('Cancel'),
        title: _lt('Error'),
        body: '',
    };

    Registries.Component.add(ErrorPopup);

    return ErrorPopup;
});
