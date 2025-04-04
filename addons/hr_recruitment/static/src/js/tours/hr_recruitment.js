odoo.define('hr_recruitment.tour', function(require) {
"use strict";

const {_t} = require('web.core');
const {Markup} = require('web.utils');
var tour = require('web_tour.tour');

tour.register('hr_recruitment_tour',{
    url: "/web",
    rainbowManMessage: _t("<div>Great job! You hired a new colleague!</div><div>Try the Website app to publish job offers online.</div>"),
    fadeout: 'very_slow',
    sequence: 230,
}, [tour.stepUtils.showAppsMenuItem(), {
    trigger: '.o_app[data-menu-xmlid="hr_recruitment.menu_hr_recruitment_root"]',
    content: Markup(_t("Let's have a look at how to <b>improve</b> your <b>hiring process</b>.")),
    position: 'right',
    edition: 'community'
}, {
    trigger: '.o_app[data-menu-xmlid="hr_recruitment.menu_hr_recruitment_root"]',
    content: Markup(_t("Let's have a look at how to <b>improve</b> your <b>hiring process</b>.")),
    position: 'bottom',
    edition: 'enterprise'
}, {
    trigger: ".o-kanban-button-new",
    content: _t("Create your first Job Position."),
    position: "bottom",
    width: 195
}, {
    trigger: ".o_job_name",
    extra_trigger: '.o_hr_job_simple_form',
    content: _t("What do you want to recruit today? Choose a job title..."),
    position: "right"
}, {
    trigger: ".o_job_alias",
    extra_trigger: '.o_hr_job_simple_form',
    content: _t("Choose an application email."),
    position: "right",
    width: 195
}, {
    trigger: '.o_create_job',
    content: _t('Let\'s create the position. An email will be setup for applications, and a public job description, if you use the Website app.'),
    position: 'bottom',
    run: function (actions) {
        actions.auto('.modal:visible .btn.btn-primary');
    },
}, {
    trigger: ".oe_kanban_action_button",
    extra_trigger: '.o_hr_recruitment_kanban',
    content: _t("Let\'s have a look at the applications pipeline."),
    position: "bottom"
}, {
    trigger: ".o_copy_paste_email",
    content: _t("Copy this email address, to paste it in your email composer, to apply."),
    position: "bottom"
}, {
    trigger: ".breadcrumb-item:not(.active):last",
    extra_trigger: '.o_kanban_applicant',
    content: _t("Let’s go back to the dashboard."),
    position: "bottom",
    width: 195
}, {
    trigger: ".oe_kanban_action_button",
    extra_trigger: '.o_hr_recruitment_kanban',
    content: Markup(_t("<b>Did you apply by sending an email?</b> Check incoming applications.")),
    position: "bottom"
}, {
    trigger: ".oe_kanban_card",
    extra_trigger: '.o_kanban_applicant',
    content: Markup(_t("<b>Drag this card</b>, to qualify him for a first interview.")),
    position: "bottom",
    run: "drag_and_drop .o_kanban_group:eq(1) ",
}, {
    trigger: ".oe_kanban_card",
    extra_trigger: '.o_kanban_applicant',
    content: Markup(_t("<b>Click to view</b> the application.")),
    position: "bottom",
    width: 195
}, {
    trigger: ".o_Chatter .o_ChatterTopbar_buttonSendMessage",
    extra_trigger: '.o_applicant_form',
    content: Markup(_t("<div><b>Try to send an email</b> to the applicant.</div><div><i>Tips: All emails sent or received are saved in the history here</i>")),
    position: "bottom"
}, {
    trigger: ".o_Chatter .o_Composer_buttonSend",
    extra_trigger: '.o_applicant_form',
    content: _t("Send your email. Followers will get a copy of the communication."),
    position: "bottom"
}, {
    trigger: ".o_Chatter .o_ChatterTopbar_buttonLogNote",
    extra_trigger: '.o_applicant_form',
    content: _t("Or talk about this applicant privately with your colleagues."),
    position: "bottom"
}, {
    trigger: ".o_create_employee",
    extra_trigger: '.o_applicant_form',
    content: _t("Let’s create this new employee now."),
    position: "bottom",
    width: 225
}, {
    trigger: ".o_form_button_save",
    extra_trigger: ".o_employee_form",
    content: _t("Save it !"),
    position: "bottom",
    width: 80
}]);

});
