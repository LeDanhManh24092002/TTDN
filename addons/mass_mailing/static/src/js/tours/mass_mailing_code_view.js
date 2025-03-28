odoo.define('mass_mailing.mass_mailing_code_view_tour', function (require) {
    "use strict";

    var tour = require('web_tour.tour');

    tour.register('mass_mailing_code_view_tour', {
        url: '/web',
        test: true,
    }, [tour.stepUtils.showAppsMenuItem(), {
        trigger: '.o_app[data-menu-xmlid="mass_mailing.mass_mailing_menu_root"]',
    }, {
        trigger: 'button.o_list_button_add',
    }, {
        trigger: 'input[name="subject"]',
        content: ('Pick the <b>email subject</b>.'),
        position: 'bottom',
        run: 'text Test',
    }, {
        trigger: 'div[name="contact_list_ids"] .o_input_dropdown > input[type="text"]',
        content: 'Click on the dropdown to open it and then start typing to search.',
    }, {
        trigger: 'li.ui-menu-item',
        content: 'Select item from dropdown',
        run: 'click',
    }, {
        trigger: 'div[name="body_arch"] iframe #default',
        content: 'Choose this <b>theme</b>.',
        run: 'click',
    }, {
        trigger: 'iframe .o_codeview_btn',
        content: ('Click here to switch to <b>code view</b>'),
        run: 'click'
    }, {
        trigger: 'iframe .o_codeview',
        content: ('Remove all content from codeview'),
        run: function () {
            const iframe = document.querySelector('.wysiwyg_iframe');
            const iframeDocument = iframe.contentWindow.document;
            let element = iframeDocument.querySelector(".o_codeview");
            element.value = '';
        }
    }, {
        trigger: 'iframe .o_codeview_btn',
        content: ('Click here to switch back from <b>code view</b>'),
        run: 'click'
    }, {
        trigger: '[name="body_arch"] iframe .o_mail_wrapper_td',
        content: 'Verify that the dropable zone was not removed',
        run: () => {},
    }, {
        trigger: '[name="body_arch"] iframe #email_designer_default_body [name="Title"] .ui-draggable-handle',
        content: 'Drag the "Title" snippet from the design panel and drop it in the editor',
        run: function (actions) {
            actions.drag_and_drop('[name="body_arch"] iframe .o_editable', this.$anchor);
        }
    }, {
        trigger: '[name="body_arch"] iframe .o_editable h1',
        content: 'Verify that the title was inserted properly in the editor',
        run: () => {},
    }, {
        trigger: 'button.o_form_button_save',
        content: 'Click on the "Save" button to save the changes.',
        run: 'click',
    }]);
});
