odoo.define('website_event.event_steps', function (require) {
"use strict";

const {_t} = require('web.core');
const {Markup} = require('web.utils');

var EventAdditionalTourSteps = require('event.event_steps');

EventAdditionalTourSteps.include({

    init: function() {
        this._super.apply(this, arguments);
    },

    _get_website_event_steps: function () {
        this._super.apply(this, arguments);
        return [{
                trigger: '.o_event_form_view button[name="is_published"]',
                content: Markup(_t("Use this <b>shortcut</b> to easily access your event web page.")),
                position: 'bottom',
            }, {
                trigger: 'li#edit-page-menu a',
                extra_trigger: '.o_wevent_event',
                content: Markup(_t("With the Edit button, you can <b>customize</b> the web page visitors will see when registering.")),
                position: 'bottom',
            }, {
                trigger: 'div[name="Image - Text"] .oe_snippet_thumbnail',
                extra_trigger: '.o_wevent_event',
                content: Markup(_t("<b>Drag and Drop</b> this snippet below the event title.")),
                position: 'bottom',
                run: 'drag_and_drop #o_wevent_event_main_col',
            }, {
                trigger: 'button[data-action="save"]',
                extra_trigger: '.o_wevent_event',
                content: Markup(_t("Don't forget to click <b>save</b> when you're done.")),
                position: 'bottom',
            }, {
                trigger: 'label.js_publish_btn',
                extra_trigger: '.o_wevent_event',
                content: Markup(_t("Looking great! Let's now <b>publish</b> this page so that it becomes <b>visible</b> on your website!")),
                position: 'bottom',
            }, {
                trigger: 'a.css_edit_dynamic',
                extra_trigger: '.js_publish_management[data-object="event.event"] .js_publish_btn .css_unpublish:visible',
                content: _t("Want to change your event configuration? Let's go back to the event form."),
                position: 'bottom',
                run: function (actions) {
                    actions.click('div.dropdown-menu a#edit-in-backend');
                },
            }, {
                trigger: 'a#edit-in-backend',
                extra_trigger: '.o_wevent_event',
                content: _t("This shortcut will bring you right back to the event form."),
                position: 'bottom'
            }];
    }
});

return EventAdditionalTourSteps;

});
