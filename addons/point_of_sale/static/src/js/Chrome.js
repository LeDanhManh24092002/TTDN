odoo.define('point_of_sale.Chrome', function(require) {
    'use strict';

    const { useState, useRef, useContext, useExternalListener } = owl.hooks;
    const { debounce } = owl.utils;
    const { loadCSS } = require('web.ajax');
    const { useListener } = require('web.custom_hooks');
    const { BarcodeEvents } = require('barcodes.BarcodeEvents');
    const PosComponent = require('point_of_sale.PosComponent');
    const NumberBuffer = require('point_of_sale.NumberBuffer');
    const PopupControllerMixin = require('point_of_sale.PopupControllerMixin');
    const Registries = require('point_of_sale.Registries');
    const IndependentToOrderScreen = require('point_of_sale.IndependentToOrderScreen');
    const contexts = require('point_of_sale.PosContext');
    const { identifyError, posbus } = require('point_of_sale.utils');
    const { odooExceptionTitleMap } = require("@web/core/errors/error_dialogs");
    const { ConnectionLostError, ConnectionAbortedError, RPCError } = require('@web/core/network/rpc_service');
    const { useBus } = require("@web/core/utils/hooks");

    // This is kind of a trick.
    // We get a reference to the whole exports so that
    // when we create an instance of one of the classes,
    // we instantiate the extended one.
    const models = require('point_of_sale.models');

    /**
     * Chrome is the root component of the PoS App.
     */
    class Chrome extends PopupControllerMixin(PosComponent) {
        constructor() {
            super(...arguments);
            useExternalListener(window, 'beforeunload', this._onBeforeUnload);
            useListener('show-main-screen', this.__showScreen);
            useListener('toggle-debug-widget', debounce(this._toggleDebugWidget, 100));
            useListener('toggle-mobile-searchbar', this._toggleMobileSearchBar);
            useListener('show-temp-screen', this.__showTempScreen);
            useListener('close-temp-screen', this.__closeTempScreen);
            useListener('close-pos', this._closePos);
            useListener('loading-skip-callback', () => this._loadingSkipCallback());
            useListener('play-sound', this._onPlaySound);
            useListener('set-sync-status', this._onSetSyncStatus);
            useListener('show-notification', this._onShowNotification);
            useListener('close-notification', this._onCloseNotification);
            useBus(posbus, 'start-cash-control', this.openCashControl);
            NumberBuffer.activate();

            this.chromeContext = useContext(contexts.chrome);

            this.state = useState({
                uiState: 'LOADING', // 'LOADING' | 'READY' | 'CLOSING'
                debugWidgetIsShown: true,
                mobileSearchBarIsShown: false,
                hasBigScrollBars: false,
                sound: { src: null },
                notification: {
                    isShown: false,
                    message: '',
                    duration: 2000,
                }
            });

            this.loading = useState({
                message: 'Loading',
                skipButtonIsShown: false,
            });

            this.mainScreen = useState({ name: null, component: null });
            this.mainScreenProps = {};

            this.tempScreen = useState({ isShown: false, name: null, component: null });
            this.tempScreenProps = {};

            this.progressbar = useRef('progressbar');

            this.previous_touch_y_coordinate = -1;
        }

        // OVERLOADED METHODS //

        mounted() {
            // remove default webclient handlers that induce click delay
            $(document).off();
            $(window).off();
            $('html').off();
            $('body').off();
            // The above lines removed the bindings, but we really need them for the barcode
            BarcodeEvents.start();
        }
        willUnmount() {
            BarcodeEvents.stop();
        }
        destroy() {
            super.destroy(...arguments);
            this.env.pos.destroy();
        }
        catchError(error) {
            console.error(error);
        }

        // GETTERS //

        get clientScreenButtonIsShown() {
            return this.env.pos.config.iface_customer_facing_display;
        }

        /**
         * Used to give the `state.mobileSearchBarIsShown` value to main screen props
         */
        get mainScreenPropsFielded() {
            return Object.assign({}, this.mainScreenProps, {
                mobileSearchBarIsShown: this.state.mobileSearchBarIsShown,
            });
        }

        /**
         * Startup screen can be based on pos config so the startup screen
         * is only determined after pos data is completely loaded.
         *
         * NOTE: Wait for pos data to be completed before calling this getter.
         */
        get startScreen() {
            if (this.state.uiState !== 'READY') {
                console.warn(
                    `Accessing startScreen of Chrome component before 'state.uiState' to be 'READY' is not recommended.`
                );
            }
            return { name: 'ProductScreen' };
        }

        // CONTROL METHODS //

        /**
         * Call this function after the Chrome component is mounted.
         * This will load pos and assign it to the environment.
         */
        async start() {
            try {
                // Instead of passing chrome to the instantiation the PosModel,
                // we inject functions needed by pos.
                // This way, we somehow decoupled Chrome from PosModel.
                // We can then test PosModel independently from Chrome by supplying
                // mocked version of these default attributes.
                const posModelDefaultAttributes = {
                    env: this.env,
                    rpc: this.rpc.bind(this),
                    session: this.env.session,
                    do_action: this.props.webClient.do_action.bind(this.props.webClient),
                    setLoadingMessage: this.setLoadingMessage.bind(this),
                    showLoadingSkip: this.showLoadingSkip.bind(this),
                    setLoadingProgress: this.setLoadingProgress.bind(this),
                };
                this.env.pos = new models.PosModel(posModelDefaultAttributes);
                await this.env.pos.ready;
                // Load the saved `env.pos.toRefundLines` from localStorage when
                // the PosModel is ready.
                Object.assign(this.env.pos.toRefundLines, this.env.pos.db.load('TO_REFUND_LINES') || {});
                this._buildChrome();
                this._closeOtherTabs();
                this.env.pos.set(
                    'selectedCategoryId',
                    this.env.pos.config.iface_start_categ_id
                        ? this.env.pos.config.iface_start_categ_id[0]
                        : 0
                );
                this.state.uiState = 'READY';
                this.env.pos.on('change:selectedOrder', this._showSavedScreen, this);
                this._showStartScreen();
                if (_.isEmpty(this.env.pos.db.product_by_category_id)) {
                    this._loadDemoData();
                }
                setTimeout(() => {
                    // push order in the background, no need to await
                    this.env.pos.push_orders();
                    // Allow using the app even if not all the images are loaded.
                    // Basically, preload the images in the background.
                    this._preloadImages();
                });
            } catch (error) {
                let title = 'Unknown Error',
                    body;

                if (error.message && [100, 200, 404, -32098].includes(error.message.code)) {
                    // this is the signature of rpc error
                    if (error.message.code === -32098) {
                        title = 'Network Failure (XmlHttpRequestError)';
                        body =
                            'The Point of Sale could not be loaded due to a network problem.\n' +
                            'Please check your internet connection.';
                    } else if (error.message.code === 200) {
                        title = error.message.data.message || this.env._t('Server Error');
                        body =
                            error.message.data.debug ||
                            this.env._t(
                                'The server encountered an error while receiving your order.'
                            );
                    }
                } else if (error instanceof Error) {
                    title = error.message;
                    body = error.stack;
                }

                await this.showPopup('ErrorTracebackPopup', {
                    title,
                    body,
                    exitButtonIsShown: true,
                });
            }
        }

        openCashControl() {
            if (this.shouldShowCashControl()) {
                this.showPopup('CashOpeningPopup', { notEscapable: true });
            }
        }

        shouldShowCashControl() {
            return this.env.pos.config.cash_control && this.env.pos.pos_session.state == 'opening_control';
        }

        // EVENT HANDLERS //

        _showStartScreen() {
            const { name, props } = this.startScreen;
            this.showScreen(name, props);
        }
        /**
         * Show the screen saved in the order when the `selectedOrder` of pos is changed.
         * @param {models.PosModel} pos
         * @param {models.Order} newSelectedOrder
         */
        _showSavedScreen(pos, newSelectedOrder) {
            const { name, props } = this._getSavedScreen(newSelectedOrder);
            this.showScreen(name, props);
        }
        _getSavedScreen(order) {
            return order.get_screen_data();
        }
        __showTempScreen(event) {
            const { name, props, resolve } = event.detail;
            this.tempScreen.isShown = true;
            this.tempScreen.name = name;
            this.tempScreen.component = this.constructor.components[name];
            this.tempScreenProps = Object.assign({}, props, { resolve });
        }
        __closeTempScreen() {
            this.tempScreen.isShown = false;
            this.tempScreen.name = null;
        }
        __showScreen({ detail: { name, props = {} } }) {
            const component = this.constructor.components[name];
            // 1. Set the information of the screen to display.
            this.mainScreen.name = name;
            this.mainScreen.component = component;
            this.mainScreenProps = props;

            // 2. Set some options
            this.chromeContext.showOrderSelector = !component.hideOrderSelector;

            // 3. Save the screen to the order.
            //  - This screen is shown when the order is selected.
            if (!(component.prototype instanceof IndependentToOrderScreen) && name !== "ReprintReceiptScreen") {
                this._setScreenData(name, props);
            }
        }
        /**
         * Set the latest screen to the current order. This is done so that
         * when the order is selected again, the ui returns to the latest screen
         * saved in the order.
         *
         * @param {string} name Screen name
         * @param {Object} props props for the Screen component
         */
        _setScreenData(name, props) {
            const order = this.env.pos.get_order();
            if (order) {
                order.set_screen_data({ name, props });
            }
        }
        async _closePos() {
            // If pos is not properly loaded, we just go back to /web without
            // doing anything in the order data.
            if (!this.env.pos || this.env.pos.db.get_orders().length === 0) {
                window.location = '/web#action=point_of_sale.action_client_pos_menu';
            }

            // If there are orders in the db left unsynced, we try to sync.
            await this.env.pos.push_orders_with_closing_popup();
            window.location = '/web#action=point_of_sale.action_client_pos_menu';
        }
        _toggleDebugWidget() {
            this.state.debugWidgetIsShown = !this.state.debugWidgetIsShown;
        }
        _toggleMobileSearchBar({ detail: isSearchBarEnabled }) {
            if (isSearchBarEnabled !== null) {
                this.state.mobileSearchBarIsShown = isSearchBarEnabled;
            } else {
                this.state.mobileSearchBarIsShown = !this.state.mobileSearchBarIsShown;
            }
        }
        _onPlaySound({ detail: name }) {
            let src;
            if (name === 'error') {
                src = "/point_of_sale/static/src/sounds/error.wav";
            } else if (name === 'bell') {
                src = "/point_of_sale/static/src/sounds/bell.wav";
            }
            this.state.sound.src = src;
        }
        _onSetSyncStatus({ detail: { status, pending }}) {
            this.env.pos.set('synch', { status, pending });
        }
        _onShowNotification({ detail: { message, duration } }) {
            this.state.notification.isShown = true;
            this.state.notification.message = message;
            this.state.notification.duration = duration;
        }
        _onCloseNotification() {
            this.state.notification.isShown = false;
            this.state.notification.message = '';
        }
        /**
         * Save `env.pos.toRefundLines` in localStorage on beforeunload - closing the
         * browser, reloading or going to other page.
         */
        _onBeforeUnload() {
            this.env.pos.db.save('TO_REFUND_LINES', this.env.pos.toRefundLines);
        }

        // TO PASS AS PARAMETERS //

        setLoadingProgress(fac) {
            if (this.progressbar.el) {
                this.progressbar.el.style.width = `${Math.floor(fac * 100)}%`;
            }
        }
        setLoadingMessage(msg, progress) {
            this.loading.message = msg;
            if (typeof progress !== 'undefined') {
                this.setLoadingProgress(progress);
            }
        }
        /**
         * Show Skip button in the loading screen and allow to assign callback
         * when the button is pressed.
         *
         * @param {Function} callback function to call when Skip button is pressed.
         */
        showLoadingSkip(callback) {
            if (callback) {
                this.loading.skipButtonIsShown = true;
                this._loadingSkipCallback = callback;
            }
        }

        get isTicketScreenShown() {
            return this.mainScreen.name === 'TicketScreen';
        }

        // MISC METHODS //

        async _loadDemoData() {
            const { confirmed } = await this.showPopup('ConfirmPopup', {
                title: this.env._t('You do not have any products'),
                body: this.env._t(
                    'Would you like to load demo data?'
                ),
                confirmText: this.env._t('Yes'),
                cancelText: this.env._t('No')
            });
            if (confirmed) {
                await this.rpc({
                    'route': '/pos/load_onboarding_data',
                });
                this.env.pos.load_server_data();
            }
        }

        _preloadImages() {
            for (let product of this.env.pos.db.get_product_by_category(0)) {
                const image = new Image();
                image.src = `/web/image?model=product.product&field=image_128&id=${product.id}&write_date=${product.write_date}&unique=1`;
            }
            for (let category of Object.values(this.env.pos.db.category_by_id)) {
                if (category.id == 0) continue;
                const image = new Image();
                image.src = `/web/image?model=pos.category&field=image_128&id=${category.id}&write_date=${category.write_date}&unique=1`;
            }
            const staticImages = ['backspace.png', 'bc-arrow-big.png'];
            for (let imageName of staticImages) {
                const image = new Image();
                image.src = `/point_of_sale/static/src/img/${imageName}`;
            }
        }

        _buildChrome() {
            if ($.browser.chrome) {
                var chrome_version = $.browser.version.split('.')[0];
                if (parseInt(chrome_version, 10) >= 50) {
                    loadCSS('/point_of_sale/static/src/css/chrome50.css');
                }
            }

            if (this.env.pos.config.iface_big_scrollbars) {
                this.state.hasBigScrollBars = true;
            }

            this._disableBackspaceBack();
        }
        // prevent backspace from performing a 'back' navigation
        _disableBackspaceBack() {
            $(document).on('keydown', function (e) {
                if (e.which === 8 && !$(e.target).is('input, textarea')) {
                    e.preventDefault();
                }
            });
        }
        _closeOtherTabs() {
            localStorage['message'] = '';
            localStorage['message'] = JSON.stringify({
                message: 'close_tabs',
                session: this.env.pos.pos_session.id,
            });

            window.addEventListener(
                'storage',
                (event) => {
                    if (event.key === 'message' && event.newValue) {
                        const msg = JSON.parse(event.newValue);
                        if (
                            msg.message === 'close_tabs' &&
                            msg.session == this.env.pos.pos_session.id
                        ) {
                            console.info(
                                'POS / Session opened in another window. EXITING POS'
                            );
                            this._closePos();
                        }
                    }
                },
                false
            );
        }
        showCashMoveButton() {
            return this.env.pos && this.env.pos.config && this.env.pos.config.cash_control;
        }

        // UNEXPECTED ERROR HANDLING //

        /**
         * This method is used to handle unexpected errors. It is registered to
         * the `error_handlers` service when this component is properly mounted.
         * See `onMounted` hook of the `ChromeAdapter` component.
         * @param {*} env
         * @param {UncaughtClientError | UncaughtPromiseError} error
         * @param {*} originalError
         * @returns {boolean}
         */
        errorHandler(env, error, originalError) {
            if (!env.pos) return false;
            const errorToHandle = identifyError(originalError);
            // Assume that the unhandled falsey rejections can be ignored.
            if (errorToHandle) {
                this._errorHandler(error, errorToHandle);
            }
            return true;
        }

        _errorHandler(error, errorToHandle) {
            if (errorToHandle instanceof RPCError) {
                const { message, data } = errorToHandle;
                if (odooExceptionTitleMap.has(errorToHandle.exceptionName)) {
                    const title = odooExceptionTitleMap.get(errorToHandle.exceptionName).toString();
                    this.showPopup('ErrorPopup', { title, body: data.message });
                } else {
                    this.showPopup('ErrorTracebackPopup', {
                        title: message,
                        body: data.message + '\n' + data.debug + '\n',
                    });
                }
            } else if (errorToHandle instanceof ConnectionLostError) {
                this.showPopup('OfflineErrorPopup', {
                    title: this.env._t('Connection is lost'),
                    body: this.env._t('Check the internet connection then try again.'),
                });
            } else if (errorToHandle instanceof ConnectionAbortedError) {
                this.showPopup('OfflineErrorPopup', {
                    title: this.env._t('Connection is aborted'),
                    body: this.env._t('Check the internet connection then try again.'),
                });
            } else if (errorToHandle instanceof Error) {
                // If `errorToHandle` is a normal Error (such as TypeError),
                // the annotated traceback can be found from `error`.
                this.showPopup('ErrorTracebackPopup', {
                    // Hopefully the message is translated.
                    title: `${errorToHandle.name}: ${errorToHandle.message}`,
                    body: error.traceback,
                });
            } else {
                // Hey developer. It's your fault that the error reach here.
                // Please, throw an Error object in order to get stack trace of the error.
                // At least we can find the file that throws the error when you look
                // at the console.
                this.showPopup('ErrorPopup', {
                    title: this.env._t('Unknown Error'),
                    body: this.env._t('Unable to show information about this error.'),
                });
                console.error('Unknown error. Unable to show information about this error.', errorToHandle);
            }
        }
        _shouldResetIdleTimer() {
            return true;
        }
    }
    Chrome.template = 'Chrome';

    Registries.Component.add(Chrome);

    return Chrome;
});
