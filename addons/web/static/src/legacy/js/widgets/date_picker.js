odoo.define('web.datepicker', function (require) {
"use strict";

var core = require('web.core');
var field_utils = require('web.field_utils');
var time = require('web.time');
var Widget = require('web.Widget');

var _t = core._t;

var DateWidget = Widget.extend({
    template: "web.datepicker",
    type_of_date: "date",
    events: {
        'error.datetimepicker': 'errorDatetime',
        'change .o_datepicker_input': 'changeDatetime',
        'click input': '_onInputClicked',
        'input input': '_onInput',
        'keydown': '_onKeydown',
        'show.datetimepicker': '_onDateTimePickerShow',
        'hide.datetimepicker': '_onDateTimePickerHide',
    },
    /**
     * @override
     */
    init: function (parent, options) {
        this._super.apply(this, arguments);

        this.name = parent.name;
        this.options = _.extend({
            locale: moment.locale(),
            format : this.type_of_date === 'datetime' ? time.getLangDatetimeFormat() : time.getLangDateFormat(),
            minDate: moment({ y: 1000 }),
            maxDate: moment({ y: 9999, M: 11, d: 31, h: 23, m: 59, s: 59 }),
            useCurrent: false,
            icons: {
                time: 'fa fa-clock-o',
                date: 'fa fa-calendar',
                up: 'fa fa-chevron-up',
                down: 'fa fa-chevron-down',
                previous: 'fa fa-chevron-left',
                next: 'fa fa-chevron-right',
                today: 'fa fa-calendar-check-o',
                clear: 'fa fa-trash',
                close: 'fa fa-check primary',
            },
            calendarWeeks: true,
            buttons: {
                showToday: false,
                showClear: false,
                showClose: false,
            },
            widgetParent: 'body',
            keyBinds: null,
        }, options || {});

        this.__libInput = 0;
        // tempusdominus doesn't offer any elegant way to check whether the
        // datepicker is open or not, so we have to listen to hide/show events
        // and manually keep track of the 'open' state
        this.__isOpen = false;
    },
    /**
     * @override
     */
    start: function () {
        this.$input = this.$('input.o_datepicker_input');
        this.__libInput++;
        this.$el.datetimepicker(this.options);
        this.__libInput--;
        this._setReadonly(false);
    },
    /**
     * @override
     */
    destroy: function () {
        if (this._onScroll) {
            window.removeEventListener('wheel', this._onScroll, true);
        }
        this.__libInput++;
        this.$el.datetimepicker('destroy');
        this.__libInput--;
        this._super.apply(this, arguments);
    },

    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------

    /**
     * set datetime value
     */
    changeDatetime: function () {
        if (this.__libInput > 0) {
            if (this.options.warn_future) {
                this._warnFuture(this.getValue());
            }
            this.trigger("datetime_changed");
            return;
        }
        var oldValue = this.getValue() || this.options.defaultDate;
        if (this.isValid()) {
            this._setValueFromUi();
            var newValue = this.getValue();
            var hasChanged = !oldValue !== !newValue;
            if (oldValue && newValue) {
                var formattedOldValue = oldValue.format(time.getLangDatetimeFormat());
                var formattedNewValue = newValue.format(time.getLangDatetimeFormat());
                if (formattedNewValue !== formattedOldValue) {
                    hasChanged = true;
                }
            }
            if (hasChanged) {
                if (this.options.warn_future) {
                    this._warnFuture(newValue);
                }
                this.trigger("datetime_changed");
            }
        } else {
            var formattedValue = oldValue ? this._formatClient(oldValue) : null;
            this.$input.val(formattedValue);
        }
    },
    /**
     * Library clears the wrong date format so just ignore error
     */
    errorDatetime: function (e) {
        return false;
    },
    /**
     * Focuses the datepicker input. This function must be called in order to
     * prevent 'input' events triggered by the lib to bubble up, and to cause
     * unwanted effects (like triggering 'field_changed' events)
     */
    focus: function () {
        this.__libInput++;
        this.$input.focus();
        this.__libInput--;
    },
    /**
     * @returns {Moment|false}
     */
    getValue: function () {
        var value = this.get('value');
        return value && value.clone();
    },
    /**
     * @returns {boolean}
     */
    isValid: function () {
        var value = this.$input.val();
        if (value === "") {
            return true;
        } else {
            try {
                this._parseClient(value);
                return true;
            } catch (e) {
                return false;
            }
        }
    },
    /**
     * @returns {Moment|false} value
     */
    maxDate: function (date) {
        this.__libInput++;
        this.$el.datetimepicker('maxDate', date || null);
        this.__libInput--;
    },
    /**
     * @returns {Moment|false} value
     */
    minDate: function (date) {
        this.__libInput++;
        this.$el.datetimepicker('minDate', date || null);
        this.__libInput--;
    },
    /**
     * @param {Moment|false} value
     */
    setValue: function (value) {
        this.set({'value': value});
        var formatted_value = value ? this._formatClient(value) : null;
        this.$input.val(formatted_value);
        this._setLibInputValue(value);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * add a warning to communicate that a date in the future has been set
     *
     * @private
     * @param {Moment} currentDate
     */
    _warnFuture: function (currentDate) {
        if (!this.$warning) {
            this.$warning = $('<span>', {
                class: 'fa fa-exclamation-triangle o_tz_warning o_datepicker_warning',
            });
            var title = _t("This date is in the future. Make sure this is what you expect.");
            this.$warning.attr('title', title);
            this.$input.after(this.$warning);
        }
        // Get rid of time and TZ crap for comparison
        if (currentDate && currentDate.format('YYYY-MM-DD') > moment().format('YYYY-MM-DD')) {
            this.$warning.show();
        } else {
            this.$warning.hide();
        }
    },

    /**
     * @private
     * @param {Moment} v
     * @returns {string}
     */
    _formatClient: function (v) {
        return field_utils.format[this.type_of_date](v, null, {timezone: false});
    },
    /**
     * @private
     * @param {string|false} v
     * @returns {Moment}
     */
    _parseClient: function (v) {
        return field_utils.parse[this.type_of_date](v, null, {timezone: false});
    },
    /**
     * @private
     * @param {Moment|false} value
     */
    _setLibInputValue: function (value) {
        this.__libInput++;
        this.$el.datetimepicker('date', value || null);
        this.__libInput--;
    },
    /**
     * @private
     * @param {boolean} readonly
     */
    _setReadonly: function (readonly) {
        this.readonly = readonly;
        this.$input.prop('readonly', this.readonly);
    },
    /**
     * set the value from the input value
     *
     * @private
     */
    _setValueFromUi: function () {
        var value = this.$input.val() || false;
        this.setValue(this._parseClient(value));
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * Reacts to the datetimepicker being hidden
     * Used to unbind the scroll event from the datetimepicker
     *
     * @private
     */
    _onDateTimePickerHide: function () {
        this.__isOpen = false;
        this.changeDatetime();
        if (this._onScroll) {
            window.removeEventListener('wheel', this._onScroll, true);
        }
        this.changeDatetime();
    },
    /**
     * Reacts to the datetimepicker being shown
     * Could set/verify our widget value
     * And subsequently update the datetimepicker
     *
     * @private
     */
    _onDateTimePickerShow: function () {
        this.__isOpen = true;
        if (this.$input.val().length !== 0 && this.isValid()) {
            this.$input.select();
        }
        var self = this;
        this._onScroll = function (ev) {
            if (ev.target !== self.$input.get(0)) {
                self.__libInput++;
                self.$el.datetimepicker('hide');
                self.__libInput--;
            }
        };
        window.addEventListener('wheel', this._onScroll, true);
    },
    /**
     * @private
     * @param {KeyEvent} ev
     */
    _onKeydown: function (ev) {
        if (ev.which === $.ui.keyCode.ESCAPE) {
            if (this.__isOpen) {
                // we don't want any other effects than closing the datepicker,
                // like leaving the edition of a row in editable list view
                ev.stopImmediatePropagation();
                this.__libInput++;
                this.$el.datetimepicker('hide');
                this.__libInput--;
                this.focus();
            }
        }
    },
    /**
     * Prevents 'input' events triggered by the library to bubble up, as they
     * might have unwanted effects (like triggering 'field_changed' events in
     * the context of field widgets)
     *
     * @private
     * @param {Event} ev
     */
    _onInput: function (ev) {
        if (this.__libInput > 0) {
            ev.stopImmediatePropagation();
        }
    },
    /**
     * @private
     */
    _onInputClicked: function () {
        this.__libInput++;
        this.$el.datetimepicker('toggle');
        this.__libInput--;
        this.focus();
    },
});

var DateTimeWidget = DateWidget.extend({
    type_of_date: "datetime",
    init: function (parent, options) {
        this._super(parent, _.extend({
            buttons: {
                showToday: false,
                showClear: false,
                showClose: true,
            },
        }, options || {}));
    },
});

return {
    DateWidget: DateWidget,
    DateTimeWidget: DateTimeWidget,
};

});
