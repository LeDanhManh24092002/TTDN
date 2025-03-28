odoo.define('stock.StockOrderpointListController', function (require) {
"use strict";

var core = require('web.core');
var ListController = require('web.ListController');
var FormView = require('web.FormView');

var qweb = core.qweb;


var StockOrderpointListController = ListController.extend({

    // -------------------------------------------------------------------------
    // Public
    // -------------------------------------------------------------------------

    /**
     * @override
     */
    renderButtons: function () {
        this._super.apply(this, arguments);
        this.$buttons.find('.o_list_export_xlsx').addClass('d-none');
        this.$buttons.find('.o_list_button_add').removeClass('btn-primary').addClass('btn-secondary');
        var $buttons = $(qweb.render('StockOrderpoint.Buttons'));
        var $buttonOrder = $buttons.find('.o_button_order');
        var $buttonSnooze = $buttons.find('.o_button_snooze');
        $buttonOrder.on('click', this._onReplenish.bind(this));
        $buttonSnooze.on('click', this._onSnooze.bind(this));
        $buttons.prependTo(this.$buttons);
    },

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    _onButtonClicked: function (ev) {
        if (ev.data.attrs.class && ev.data.attrs.class.split(' ').includes('o_replenish_buttons')) {
            ev.stopPropagation();
            this.trigger_up('save_line', {
                recordID: ev.data.record.id,
                onSuccess: () => this._callButtonAction(ev.data.attrs, ev.data.record).then(() => this.reload())
            });
        } else {
            this._super.apply(this, arguments);
        }
    },

    _onReplenish: function () {
        this.getSelectedIdsWithDomain().then(ids => this.model.replenish((ids)));
    },

    _onSelectionChanged: function (ev) {
        this._super(ev);
        var $buttonOrder = this.$el.find('.o_button_order');
        var $buttonSnooze = this.$el.find('.o_button_snooze');
        if (this.getSelectedIds().length === 0){
            $buttonOrder.addClass('d-none');
            $buttonSnooze.addClass('d-none');
        } else {
            $buttonOrder.removeClass('d-none');
            $buttonSnooze.removeClass('d-none');
        }
    },

    _onSnooze: function () {
        this.getSelectedIdsWithDomain().then(ids => this.model.snooze((ids)));
    },
});

return StockOrderpointListController;

});
