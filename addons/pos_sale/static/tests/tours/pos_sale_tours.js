odoo.define('pos_sale.tour', function (require) {
    'use strict';

    const { Chrome } = require('point_of_sale.tour.ChromeTourMethods');
    const { PaymentScreen } = require('point_of_sale.tour.PaymentScreenTourMethods');
    const { ProductScreen } = require('pos_sale.tour.ProductScreenTourMethods');
    const { ReceiptScreen } = require('pos_sale.tour.ReceiptScreenTourMethods');
    const { TicketScreen } = require('point_of_sale.tour.TicketScreenTourMethods');
    const { getSteps, startSteps } = require('point_of_sale.tour.utils');
    const Tour = require('web_tour.tour');

    // signal to start generating steps
    // when finished, steps can be taken from getSteps
    startSteps();

    ProductScreen.do.confirmOpeningPopup();
    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.selectFirstOrder();
    ProductScreen.check.selectedOrderlineHas('Pizza Chicken', 9);
    ProductScreen.do.pressNumpad('Qty 2'); // Change the quantity of the product to 2
    ProductScreen.check.selectedOrderlineHas('Pizza Chicken', 2);
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Bank');
    PaymentScreen.do.clickValidate();
    Chrome.do.clickTicketButton();

    Tour.register('PosSettleOrder', { test: true, url: '/pos/ui' }, getSteps());

    startSteps();

    ProductScreen.do.confirmOpeningPopup();
    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.selectFirstOrder();
    ProductScreen.do.clickOrderline('[A001] Product A', '1');
    ProductScreen.check.selectedOrderlineHas('[A001] Product A', '1.00');
    ProductScreen.do.clickOrderline('[A002] Product B', '1');
    ProductScreen.do.pressNumpad('Qty 0');
    ProductScreen.check.selectedOrderlineHas('[A002] Product B', '0.00');
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Bank');
    PaymentScreen.check.remainingIs('0.0');
    PaymentScreen.do.clickValidate();
    ReceiptScreen.check.isShown();

    Tour.register('PosSettleOrder2', { test: true, url: '/pos/ui' }, getSteps());

    startSteps();

    ProductScreen.do.confirmOpeningPopup();
    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.selectFirstOrder();
    ProductScreen.do.clickOrderline("Product A", "1");
    ProductScreen.check.selectedOrderlineHas('Product A', '1.00');
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Bank');
    PaymentScreen.check.remainingIs('0.0');
    PaymentScreen.do.clickValidate();
    ReceiptScreen.check.isShown();

    Tour.register('PosSettleOrder3', { test: true, url: '/pos/ui' }, getSteps());

    startSteps();

    ProductScreen.do.confirmOpeningPopup();
    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.selectFirstOrder();
    ProductScreen.check.totalAmountIs(100);

    Tour.register('PosSettleOrderWithPromotions', { test: true, url: '/pos/ui' }, getSteps());

    startSteps();

    ProductScreen.do.confirmOpeningPopup();
    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.selectFirstOrder();
    ProductScreen.check.totalAmountIs(40);
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Bank');
    PaymentScreen.do.clickValidate();
    Chrome.do.clickTicketButton();

    Tour.register('PosSettleOrderRealTime', { test: true, url: '/pos/ui' }, getSteps());

    startSteps();

    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.downPaymentFirstOrder();
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Cash');
    PaymentScreen.do.clickValidate();
    ReceiptScreen.do.clickNextOrder();
    ProductScreen.do.clickRefund();
    // Filter should be automatically 'Paid'.
    TicketScreen.check.filterIs('Paid');
    TicketScreen.do.selectOrder('-0001');
    TicketScreen.do.clickOrderline('Down Payment');
    TicketScreen.do.pressNumpad('1');
    TicketScreen.do.confirmRefund();
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Cash');
    PaymentScreen.do.clickValidate();
    ReceiptScreen.do.clickNextOrder();

    Tour.register('PosRefundDownpayment', { test: true, url: '/pos/ui' }, getSteps());

    startSteps();

    ProductScreen.do.clickQuotationButton();
    ProductScreen.do.selectFirstOrder();
    ProductScreen.check.checkCustomerNotes("Customer note 2--Customer note 3");
    ProductScreen.do.clickPayButton();
    PaymentScreen.do.clickPaymentMethod('Bank');
    PaymentScreen.do.clickValidate();
    ReceiptScreen.check.checkCustomerNotes("Customer note 2--Customer note 3");
    ReceiptScreen.do.clickNextOrder();

    Tour.register('PosSettleOrderWithNote', { test: true, url: '/pos/ui' }, getSteps());

});
