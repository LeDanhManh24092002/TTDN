odoo.define('web.KanbanRecord', function (require) {
"use strict";

/**
 * This file defines the KanbanRecord widget, which corresponds to a card in
 * a Kanban view.
 */
var config = require('web.config');
var core = require('web.core');
var Domain = require('web.Domain');
var Dialog = require('web.Dialog');
var field_utils = require('web.field_utils');
const FieldWrapper = require('web.FieldWrapper');
var utils = require('web.utils');
var Widget = require('web.Widget');
const { WidgetAdapterMixin } = require('web.OwlCompatibility');
var widgetRegistry = require('web.widget_registry');
const widgetRegistryOwl = require('web.widgetRegistry');
const WidgetWrapper = require("web.WidgetWrapper");

var _t = core._t;
var QWeb = core.qweb;

var KANBAN_RECORD_COLORS = require('web.basic_fields').FieldColorPicker.prototype.RECORD_COLORS;
var NB_KANBAN_RECORD_COLORS = KANBAN_RECORD_COLORS.length;

var KanbanRecord = Widget.extend(WidgetAdapterMixin, {
    events: {
        'click .oe_kanban_action': '_onKanbanActionClicked',
        'click .o_kanban_manage_toggle_button': '_onManageTogglerClicked',
    },
    /**
     * @override
     */
    init: function (parent, state, options) {
        this._super(parent);

        this.fields = state.fields;
        this.fieldsInfo = state.fieldsInfo.kanban;
        this.modelName = state.model;

        this.options = options;
        this.editable = options.editable;
        this.deletable = options.deletable;
        this.read_only_mode = options.read_only_mode;
        this.selectionMode = options.selectionMode;
        this.qweb = options.qweb;
        this.subWidgets = {};

        this._setState(state);
        // avoid quick multiple clicks
        this._onKanbanActionClicked = _.debounce(this._onKanbanActionClicked, 300, true);
    },
    /**
     * @override
     */
    start: function () {
        return Promise.all([this._super.apply(this, arguments), this._render()]);
    },
    /**
     * @override
     */
    destroy: function () {
        this._super(...arguments);
        WidgetAdapterMixin.destroy.call(this);
    },
    /**
     * Called each time the record is attached to the DOM.
     */
    on_attach_callback: function () {
        this.isInDOM = true;
        _.invoke(this.subWidgets, 'on_attach_callback');
        // call on_attach_callback on child components (tag <widget>)
        WidgetAdapterMixin.on_attach_callback.call(this);
    },
    /**
     * Called each time the record is detached from the DOM.
     */
    on_detach_callback: function () {
        this.isInDOM = false;
        _.invoke(this.subWidgets, 'on_detach_callback');
        // call on_detach_callback on child components (tag <widget>)
        WidgetAdapterMixin.on_detach_callback.call(this);
    },

    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------

    /**
     * Check if a html content is empty. If there are only formatting tags with
     * style attributes or a void content. Famous use case is
     * '<p style="..." class=".."><br></p>' added by some web editor(s).
     * Note that because the use of this method is limited, we ignore the cases
     * like there's one <img> tag in the content. In such case, even if it's the
     * actual content, we consider it empty.
     *
     * @param {string} htmlContent
     * @returns {boolean} true if no content found or if containing only formatting tags
     */
    isHtmlEmpty: function (htmlContent) {
        let div = document.createElement('div');
        div.innerHTML = htmlContent || "";
        return div.innerText.trim() === "";
    },
    /**
     * Re-renders the record with a new state
     *
     * @param {Object} state
     * @returns {Promise}
     */
    update: function (state) {
        // detach the widgets because the record will empty its $el, which will
        // remove all event handlers on its descendants, and we want to keep
        // those handlers alive as we will re-use these widgets
        _.invoke(_.pluck(this.subWidgets, '$el'), 'detach');
        this._setState(state);
        return this._render();
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * @private
     */
    _attachTooltip: function () {
        var self = this;
        this.$('[tooltip]').each(function () {
            var $el = $(this);
            var tooltip = $el.attr('tooltip');
            if (tooltip) {
                $el.tooltip({
                    title: self.qweb.render(tooltip, self.qweb_context)
                });
            }
        });
    },
    /**
     * @private
     * @param {string} d a stringified domain
     * @returns {boolean} the domain evaluted with the current values
     */
    _computeDomain: function (d) {
        return new Domain(d).compute(this.state.evalContext);
    },
    /**
     * Generates the color classname from a given variable
     *
     * @private
     * @param {number | string} variable
     * @return {string} the classname
     */
    _getColorClassname: function (variable) {
        var color = this._getColorID(variable);
        return 'oe_kanban_color_' + color;
    },
    /**
     * Computes a color id between 0 and 10 from a given value
     *
     * @private
     * @param {number | string} variable
     * @returns {integer} the color id
     */
    _getColorID: function (variable) {
        if (typeof variable === 'number') {
            return Math.round(variable) % NB_KANBAN_RECORD_COLORS;
        }
        if (typeof variable === 'string') {
            var index = 0;
            for (var i = 0; i < variable.length; i++) {
                index += variable.charCodeAt(i);
            }
            return index % NB_KANBAN_RECORD_COLORS;
        }
        return 0;
    },
    /**
     * Computes a color name from value
     *
     * @private
     * @param {number | string} variable
     * @returns {integer} the color name
     */
    _getColorname: function (variable) {
        var colorID = this._getColorID(variable);
        return KANBAN_RECORD_COLORS[colorID];
    },
    file_type_magic_word: {
        '/': 'jpg',
        'R': 'gif',
        'i': 'png',
        'P': 'svg+xml',
    },
    /**
     * @private
     * @param {string} model the name of the model
     * @param {string} field the name of the field
     * @param {integer} id the id of the resource
     * @param {string} placeholder
     * @returns {string} the url of the image
     */
    _getImageURL: function (model, field, id, placeholder) {
        id = (_.isArray(id) ? id[0] : id) || null;
        var isCurrentRecord = this.modelName === model && (this.recordData.id === id || (!this.recordData.id && !id));
        var url;
        if (isCurrentRecord && this.record[field] && this.record[field].raw_value && !utils.is_bin_size(this.record[field].raw_value)) {
            // Use magic-word technique for detecting image type
            url = 'data:image/' + this.file_type_magic_word[this.record[field].raw_value[0]] + ';base64,' + this.record[field].raw_value;
        } else if (placeholder && (!model || !field || !id || (isCurrentRecord && this.record[field] && !this.record[field].raw_value))) {
            url = placeholder;
        } else {
            var session = this.getSession();
            var params = {
                model: model,
                field: field,
                id: id
            };
            if (isCurrentRecord) {
                params.unique = this.record.__last_update && this.record.__last_update.value.replace(/[^0-9]/g, '');
            }
            url = session.url('/web/image', params);
        }
        return url;
    },
    /**
     * Triggers up an event to open the record
     *
     * @private
     */
    _openRecord: function () {
        var editMode = this.$el.hasClass('oe_kanban_global_click_edit');
        this.trigger_up('open_record', {
            id: this.db_id,
            mode: editMode ? 'edit' : 'readonly',
        });
    },
    /**
     * Processes each 'field' tag and replaces it by the specified widget, if
     * any, or directly by the formatted value
     *
     * @private
     */
    _processFields: function () {
        var self = this;
        this.$("field").each(function () {
            var $field = $(this);
            var field_name = $field.attr("name");
            var field_widget = $field.attr("widget");

            // a widget is specified for that field or a field is a many2many ;
            // in this latest case, we want to display the widget many2manytags
            // even if it is not specified in the view.
            if (field_widget || self.fields[field_name].type === 'many2many') {
                var widget = self.subWidgets[field_name];
                if (!widget) {
                    // the widget doesn't exist yet, so instanciate it
                    var Widget = self.fieldsInfo[field_name].Widget;
                    if (Widget) {
                        widget = self._processWidget($field, field_name, Widget);
                        self.subWidgets[field_name] = widget;
                    } else if (config.isDebug()) {
                        // the widget is not implemented
                        $field.replaceWith($('<span>', {
                            text: _.str.sprintf(_t('[No widget %s]'), field_widget),
                        }));
                    }
                } else {
                    // a widget already exists for that field, so reset it with the new state
                    widget.reset(self.state);
                    $field.replaceWith(widget.$el);
                    if (self.isInDOM && widget.on_attach_callback) {
                        widget.on_attach_callback();
                    }
                }
            } else {
                self._processField($field, field_name);
            }
        });
    },
    /**
     * Replace a field by its formatted value.
     *
     * @private
     * @param {JQuery} $field
     * @param {String} field_name
     * @returns {Jquery} the modified node
     */
    _processField: function ($field, field_name) {
        // no widget specified for that field, so simply use a formatter
        // note: we could have used the widget corresponding to the field's type, but
        // it is much more efficient to use a formatter
        var field = this.fields[field_name];
        var value = this.recordData[field_name];
        var options = { data: this.recordData, forceString: true };
        var formatted_value = field_utils.format[field.type](value, field, options);
        var $result = $('<span>', {
            text: formatted_value,
        });
        $field.replaceWith($result);
        this._setFieldDisplay($result, field_name);
        return $result;
    },
    /**
     * Replace a field by its corresponding widget.
     *
     * @private
     * @param {JQuery} $field
     * @param {String} field_name
     * @param {Class} Widget
     * @returns {Widget} the widget instance
     */
    _processWidget: function ($field, field_name, Widget) {
        // some field's attrs might be record dependent (they start with
        // 't-att-') and should thus be evaluated, which is done by qweb
        // we here replace those attrs in the dict of attrs of the state
        // by their evaluted value, to make it transparent from the
        // field's widgets point of view
        // that dict being shared between records, we don't modify it
        // in place
        var self = this;
        var attrs = Object.create(null);
        _.each(this.fieldsInfo[field_name], function (value, key) {
            if (_.str.startsWith(key, 't-att-')) {
                key = key.slice(6);
                value = $field.attr(key);
            }
            attrs[key] = value;
        });
        var options = _.extend({}, this.options, { attrs: attrs });
        let widget;
        let def;
        if (utils.isComponent(Widget)) {
            widget = new FieldWrapper(this, Widget, {
                fieldName: field_name,
                record: this.state,
                options: options,
            });
            def = widget.mount(document.createDocumentFragment())
                .then(() => {
                    $field.replaceWith(widget.$el);
                });
        } else {
            widget = new Widget(this, field_name, this.state, options);
            def = widget.replace($field);
        }
        this.defs.push(def);
        def.then(function () {
            self._setFieldDisplay(widget.$el, field_name);
        });
        return widget;
    },
    _processWidgets: function () {
        var self = this;
        this.$("widget").each(function () {
            var $field = $(this);

            const attrs = {};
            for (const attr of $field[0].attributes) {
                attrs[attr.name] = attr.value;
            }
            const options = Object.assign({}, self.options, { attrs });

            const name = $field.attr('name');
            const Widget = widgetRegistryOwl.get(name) || widgetRegistry.get(name);
            const legacy = !(Widget.prototype instanceof owl.Component);
            let widget;
            if (legacy) {
                widget = new Widget(self, self.state, options);
            } else {
                widget = new WidgetWrapper(this, Widget, { record: self.state, options });
            }
            // Prepare widget rendering and save the related promise
            let def;
            if (legacy) {
                def = widget._widgetRenderAndInsert(function () { });
            } else {
                def = widget.mount(document.createDocumentFragment());
            }

            self.defs.push(def);
            def.then(function () {
                $field.replaceWith(widget.$el);
                widget.$el.addClass('o_widget');
            });
        });
    },
    /**
     * Renders the record
     *
     * @returns {Promise}
     */
    _render: function () {
        this.defs = [];
        // call 'on_detach_callback' on each subwidget as they will be removed
        // from the DOM at the next line
        _.invoke(this.subWidgets, 'on_detach_callback');
        this._replaceElement(this.qweb.render('kanban-box', this.qweb_context));
        this.$el.addClass('o_kanban_record').attr("tabindex", 0);
        this.$el.attr('role', 'article');
        this.$el.data('record', this);
        // forcefully add class oe_kanban_global_click to have clickable record always to select it
        if (this.selectionMode) {
            this.$el.addClass('oe_kanban_global_click');
        }
        if (this.$el.hasClass('oe_kanban_global_click') ||
            this.$el.hasClass('oe_kanban_global_click_edit')) {
            this.$el.on('click', this._onGlobalClick.bind(this));
            this.$el.on('keydown', this._onKeyDownCard.bind(this));
        } else {
            this.$el.on('keydown', this._onKeyDownOpenFirstLink.bind(this));
        }
        this._processFields();
        this._processWidgets();
        this._setupColor();
        this._setupColorPicker();
        this._attachTooltip();

        // We use boostrap tooltips for better and faster display
        this.$('span.o_tag').tooltip({ delay: { 'show': 50 } });

        return Promise.all(this.defs);
    },
    /**
     * Sets cover image on a kanban card through an attachment dialog.
     *
     * @private
     * @param {string} fieldName field used to set cover image
     * @param {boolean} autoOpen automatically open the file choser if there are no attachments
     */
    _setCoverImage: function (fieldName, autoOpen) {
        var self = this;
        this._rpc({
            model: 'ir.attachment',
            method: 'search_read',
            domain: [
                ['res_model', '=', this.modelName],
                ['res_id', '=', this.id],
                ['mimetype', 'ilike', 'image']
            ],
            fields: ['id', 'name'],
        }).then(function (attachmentIds) {
            self.imageUploadID = _.uniqueId('o_cover_image_upload');
            self.accepted_file_extensions = 'image/*';  // prevent uploading of other file types
            self.attachment_count = attachmentIds.length;
            var coverId = self.record[fieldName] && self.record[fieldName].raw_value;
            var $content = $(QWeb.render('KanbanView.SetCoverModal', {
                coverId: coverId,
                attachmentIds: attachmentIds,
                widget: self,
            }));
            var $imgs = $content.find('.o_kanban_cover_image');
            var dialog = new Dialog(self, {
                title: _t("Set a Cover Image"),
                $content: $content,
                buttons: [{
                    text: _t("Select"),
                    classes: attachmentIds.length ? 'btn-primary' : 'd-none',
                    close: true,
                    disabled: !coverId,
                    click: function () {
                        var $img = $imgs.filter('.o_selected').find('img');
                        var data = {};
                        data[fieldName] = {
                            id: $img.data('id'),
                            display_name: $img.data('name')
                        };
                        self.trigger_up('kanban_record_update', data);
                    },
                }, {
                    text: _t('Upload and Set'),
                    classes: attachmentIds.length ? '' : 'btn-primary',
                    close: false,
                    click: function () {
                        $content.find('input.o_input_file').click();
                    },
                }, {
                    text: _t("Remove Cover Image"),
                    classes: coverId ? '' : 'd-none',
                    close: true,
                    click: function () {
                        var data = {};
                        data[fieldName] = false;
                        self.trigger_up('kanban_record_update', data);
                    },
                }, {
                    text: _t("Discard"),
                    close: true,
                }],
            });
            dialog.opened().then(function () {
                var $selectBtn = dialog.$footer.find('.btn-primary');
                if (autoOpen && !self.attachment_count) {
                    $selectBtn.click();
                }

                $content.on('click', '.o_kanban_cover_image', function (ev) {
                    $imgs.not(ev.currentTarget).removeClass('o_selected');
                    $selectBtn.prop('disabled', !$(ev.currentTarget).toggleClass('o_selected').hasClass('o_selected'));
                });

                $content.on('dblclick', '.o_kanban_cover_image', function (ev) {
                    var $img  = $(ev.currentTarget).find('img');
                    var data = {};
                    data[fieldName] = {
                        id: $img.data('id'),
                        display_name: $img.data('name')
                    };
                    self.trigger_up('kanban_record_update', data);
                    dialog.close();
                });
                $content.on('change', 'input.o_input_file', function () {
                    $content.find('form.o_form_binary_form').submit();
                });
                $(window).on(self.imageUploadID, function () {
                    var images = Array.prototype.slice.call(arguments, 1);
                    var data = {};
                    data[fieldName] = {
                        id: images[0].id,
                        display_name: images[0].filename
                    };
                    self.trigger_up('kanban_record_update', data);
                    dialog.close();
                });
            });
            dialog.open();
        });
    },
    /**
     * Sets particular classnames on a field $el according to the
     * field's attrs (display or bold attributes)
     *
     * @private
     * @param {JQuery} $el
     * @param {string} fieldName
     */
    _setFieldDisplay: function ($el, fieldName) {
        // attribute display
        if (this.fieldsInfo[fieldName].display === 'right') {
            $el.addClass('float-right');
        } else if (this.fieldsInfo[fieldName].display === 'full') {
            $el.addClass('o_text_block');
        }

        // attribute bold
        if (this.fieldsInfo[fieldName].bold) {
            $el.addClass('o_text_bold');
        }
    },
    /**
     * Sets internal values of the kanban record according to the given state
     *
     * @private
     * @param {Object} recordState
     */
    _setState: function (recordState) {
        this.state = recordState;
        this.id = recordState.res_id;
        this.db_id = recordState.id;
        this.recordData = recordState.data;
        this.record = this._transformRecord(recordState.data);
        this.qweb_context = {
            context: this.state.getContext(),
            kanban_image: this._getImageURL.bind(this),
            kanban_color: this._getColorClassname.bind(this),
            kanban_getcolor: this._getColorID.bind(this),
            kanban_getcolorname: this._getColorname.bind(this),
            kanban_compute_domain: this._computeDomain.bind(this),
            selection_mode: this.selectionMode,
            read_only_mode: this.read_only_mode,
            record: this.record,
            user_context: this.getSession().user_context,
            widget: this,
        };
    },
    /**
     * If an attribute `color` is set on the kanban record, adds the
     * corresponding color classname.
     *
     * @private
     */
    _setupColor: function () {
        var color_field = this.$el.attr('color');
        if (color_field && color_field in this.fields) {
            var colorHelp = _.str.sprintf(_t("Card color: %s"), this._getColorname(this.recordData[color_field]));
            var colorClass = this._getColorClassname(this.recordData[color_field]);
            this.$el.addClass(colorClass);
            this.$el.prepend('<span title="' + colorHelp + '" aria-label="' + colorHelp + '" role="img" class="oe_kanban_color_help"/>');
        }
    },
    /**
     * Renders the color picker in the kanban record, and binds the event handler
     *
     * @private
     */
    _setupColorPicker: function () {
        var $colorpicker = this.$('ul.oe_kanban_colorpicker');
        if (!$colorpicker.length) {
            return;
        }
        $colorpicker.html(QWeb.render('KanbanColorPicker', { colors: KANBAN_RECORD_COLORS}));
        $colorpicker.on('click', 'a', this._onColorChanged.bind(this));
    },
    /**
     * Builds an object containing the formatted record data used in the
     * template
     *
     * @private
     * @param {Object} recordData
     * @returns {Object} transformed record data
     */
    _transformRecord: function (recordData) {
        const new_record = Object.create(null);
        for (const name of this.state.getFieldNames()) {
            const value = recordData[name];
            const r = new_record[name] = _.clone(this.fields[name] || {});
            const formatter = r.type ? field_utils.format[r.type] : _.identity;

            r.raw_value = value;
            r.value = formatter(value, this.fields[name], recordData, this.state);
            switch (r.type) {
            case 'date': case 'datetime':
                r.raw_value = value && value.toDate();
                break;
            case 'one2many': case 'many2many':
                r.raw_value = value.count ? value.res_ids : [];
                break;
            case 'many2one':
                r.raw_value = value && value.res_id || false;
                break;
            case 'html': // or should this be in `format` instead of _.identity?
                r.value = utils.Markup(value);
                break;
            }
        }
        return new_record;
    },
    /**
     * Notifies the controller that the record has changed
     *
     * @private
     * @param {Object} data the new values
     */
    _updateRecord: function (data) {
        this.trigger_up('kanban_record_update', data);
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * @private
     * @param {MouseEvent} event
     */
    _onColorChanged: function (event) {
        event.preventDefault();
        var data = {};
        var color_field = $(event.delegateTarget).data('field') || 'color';
        data[color_field] = $(event.currentTarget).data('color');
        this.trigger_up('kanban_record_update', data);
    },
    /**
     * @private
     * @param {MouseEvent} event
     */
    _onGlobalClick: function (event) {
        if ($(event.target).parents('.o_dropdown_kanban').length) {
            return;
        }
        if (this.$el.hasClass('o_currently_dragged')) {
            // this record is currently being dragged and dropped, so we do not
            // want to open it.
            return;
        }
        var trigger = true;
        var elem = event.target;
        var ischild = true;
        var children = [];
        while (elem) {
            var events = $._data(elem, 'events');
            if (elem === event.currentTarget) {
                ischild = false;
            }
            var test_event = events && events.click && (events.click.length > 1 || events.click[0].namespace !== 'bs.tooltip');
            var testLinkWithHref = elem.nodeName.toLowerCase() === 'a' && elem.href;
            if (ischild) {
                children.push(elem);
                if (test_event || testLinkWithHref) {
                    // Do not trigger global click if one child has a click
                    // event registered (or it is a link with href)
                    trigger = false;
                }
            }
            if (trigger && test_event) {
                _.each(events.click, function (click_event) {
                    if (click_event.selector) {
                        // For each parent of original target, check if a
                        // delegated click is bound to any previously found children
                        _.each(children, function (child) {
                            if ($(child).is(click_event.selector)) {
                                trigger = false;
                            }
                        });
                    }
                });
            }
            elem = elem.parentElement;
        }
        if (trigger) {
            this._openRecord();
        }
    },
    /**
     * @private
     * @param {MouseEvent} event
     */
    _onKanbanActionClicked: function (event) {
        event.preventDefault();

        var $action = $(event.currentTarget);
        var type = $action.data('type') || 'button';

        switch (type) {
            case 'edit':
                this.trigger_up('open_record', { id: this.db_id, mode: 'edit' });
                break;
            case 'open':
                this.trigger_up('open_record', { id: this.db_id });
                break;
            case 'delete':
                this.trigger_up('kanban_record_delete', { id: this.db_id, record: this });
                break;
            case 'action':
            case 'object':
                var attrs = $action.data();
                attrs.confirm = $action.attr('confirm');
                this.trigger_up('button_clicked', {
                    attrs: attrs,
                    record: this.state,
                });
                break;
            case 'set_cover':
                var fieldName = $action.data('field');
                var autoOpen = $action.data('auto-open');
                if (this.fields[fieldName].type === 'many2one' &&
                    this.fields[fieldName].relation === 'ir.attachment' &&
                    this.fieldsInfo[fieldName].widget === 'attachment_image') {
                    this._setCoverImage(fieldName, autoOpen);
                } else {
                    var warning = _.str.sprintf(_t('Could not set the cover image: incorrect field ("%s") is provided in the view.'), fieldName);
                    this.displayNotification({ title: warning, type: 'danger' });
                }
                break;
            default:
                this.displayNotification({ message: _t("Kanban: no action for type: ") + type, type: 'danger' });
        }
    },
    /**
     * This event is linked to the kanban card when there is a global_click
     * class on this card
     *
     * @private
     * @param {KeyDownEvent} event
     */
    _onKeyDownCard: function (event) {
        switch (event.keyCode) {
            case $.ui.keyCode.ENTER:
                if ($(event.target).hasClass('oe_kanban_global_click')) {
                    event.preventDefault();
                    this._onGlobalClick(event);
                    break;
                }
        }
    },
    /**
     * This event is linked ot the kanban card when there is no global_click
     * class on the card
     *
     * @private
     * @param {KeyDownEvent} event
     */
    _onKeyDownOpenFirstLink: function (event) {
        switch (event.keyCode) {
            case $.ui.keyCode.ENTER:
                event.preventDefault();
                $(event.target).find('a, button').first().click();
                break;
        }
    },
    /**
     * Toggles the configuration panel of the record
     *
     * @private
     * @param {MouseEvent} event
     */
    _onManageTogglerClicked: function (event) {
        event.preventDefault();
        this.$el.parent().find('.o_kanban_record').not(this.$el).removeClass('o_dropdown_open');
        this.$el.toggleClass('o_dropdown_open');
        var colorClass = this._getColorClassname(this.recordData.color || 0);
        this.$('.o_kanban_manage_button_section').toggleClass(colorClass);
    },
});

return KanbanRecord;

});
