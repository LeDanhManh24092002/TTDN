odoo.define('website.wysiwyg', function (require) {
'use strict';

var Wysiwyg = require('web_editor.wysiwyg');
var snippetsEditor = require('web_editor.snippet.editor');
const { cloneContentEls } = require("website.utils");
const weWidgets = require('wysiwyg.widgets');

/**
 * Show/hide the dropdowns associated to the given toggles and allows to wait
 * for when it is fully shown/hidden.
 *
 * Note: this also takes care of the fact the 'toggle' method of bootstrap does
 * not properly work in all cases.
 *
 * @param {jQuery} $toggles
 * @param {boolean} [show]
 * @returns {Promise<jQuery>}
 */
function toggleDropdown($toggles, show) {
    return Promise.all(_.map($toggles, toggle => {
        var $toggle = $(toggle);
        var $dropdown = $toggle.parent();
        var shown = $dropdown.hasClass('show');
        if (shown === show) {
            return;
        }
        var toShow = !shown;
        return new Promise(resolve => {
            $dropdown.one(
                toShow ? 'shown.bs.dropdown' : 'hidden.bs.dropdown',
                () => resolve()
            );
            $toggle.dropdown(toShow ? 'show' : 'hide');
        });
    })).then(() => $toggles);
}

/**
 * Checks if the classes that changed during the mutation are all to be ignored.
 * (The mutation can be discarded if it is the case, when filtering the mutation
 * records).
 *
 * @param {Object} record the current mutation
 * @param {Array} excludedClasses the classes to ignore
 * @returns {Boolean}
 */
function checkForExcludedClasses(record, excludedClasses) {
    const classBefore = (record.oldValue && record.oldValue.split(" ")) || [];
    const classAfter = [...record.target.classList];
    const changedClasses = [
        ...classBefore.filter(c => c && !classAfter.includes(c)),
        ...classAfter.filter(c => c && !classBefore.includes(c)),
    ];
    return changedClasses.every(c => excludedClasses.includes(c));
}

/**
 * HtmlEditor
 * Intended to edit HTML content. This widget uses the Wysiwyg editor
 * improved by odoo.
 *
 * class editable: o_editable
 * class non editable: o_not_editable
 *
 */
Wysiwyg.include({
    /**
     * @override
     */
    start: async function () {
        this.options.toolbarHandler = $('#web_editor-top-edit');

        // Dropdown menu initialization: handle dropdown openings by hand
        var $dropdownMenuToggles = this.$('.o_mega_menu_toggle, #top_menu_container .dropdown-toggle:not(.o_extra_menu_items_toggle)');
        $dropdownMenuToggles.removeAttr('data-toggle').dropdown('dispose');
        $dropdownMenuToggles.on('click.wysiwyg_megamenu', ev => {
            var $toggle = $(ev.currentTarget);

            // Each time we toggle a dropdown, we will destroy the dropdown
            // behavior afterwards to keep manual control of it
            var dispose = ($els => $els.dropdown('dispose'));

            // First hide all other dropdown menus
            toggleDropdown($dropdownMenuToggles.not($toggle), false).then(dispose);

            // Then toggle the clicked one
            toggleDropdown($toggle)
                .then(dispose)
                .then(() => {
                    if (!this.options.enableTranslation) {
                        this._toggleMegaMenu($toggle[0]);
                    }
                });
        });

        // Ensure :blank oe_structure elements are in fact empty as ':blank'
        // does not really work with all browsers.
        for (const el of this.$('.oe_structure')) {
            if (!el.innerHTML.trim()) {
                $(el).empty();
            }
        }

        const ret = await this._super.apply(this, arguments);

        // Overriding the `filterMutationRecords` function so it can be used to
        // filter website-specific mutations.
        const webEditorFilterMutationRecords = this.odooEditor.options.filterMutationRecords;
        Object.assign(this.odooEditor.options, {
            /**
             * @override
             */
            filterMutationRecords(records) {
                const filteredRecords = webEditorFilterMutationRecords(records);

                // Dropdown attributes to ignore.
                const dropdownClasses = ["show", "dropdown-menu-left", "dropdown-menu-right"];
                const dropdownToggleAttributes = ["aria-expanded"];
                const dropdownMenuAttributes = ["style"];
                // Collapse attributes to ignore.
                const collapseClasses = ["show", "collapse", "collapsing", "collapsed"];
                const collapseAttributes = ["style", "aria-expanded"];
                const collapseTogglerAttributes = ["aria-expanded"];
                // Extra menu attributes to ignore.
                const extraMenuClasses = ["nav-item", "nav-link", "dropdown-item", "active"];

                return filteredRecords.filter(record => {
                    if (record.type === "attributes") {
                        if (record.target.closest("header#top")) {
                            // Do not record when showing/hiding a dropdown.
                            if (record.target.matches(".dropdown, .dropdown-menu")
                                    && record.attributeName === "class") {
                                if (checkForExcludedClasses(record, dropdownClasses)) {
                                    return false;
                                }
                            } else if (record.target.matches(".dropdown-menu")
                                    && dropdownMenuAttributes.includes(record.attributeName)) {
                                return false;
                            } else if (record.target.matches(".dropdown-toggle")
                                    && dropdownToggleAttributes.includes(record.attributeName)) {
                                return false;
                            }

                            // Do not record when showing/hiding a collapse.
                            if (record.target.matches(".navbar-collapse, .navbar-toggler")
                                    && record.attributeName === "class") {
                                if (checkForExcludedClasses(record, collapseClasses)) {
                                    return false;
                                }
                            } else if (record.target.matches(".navbar-collapse")
                                    && collapseAttributes.includes(record.attributeName)) {
                                return false;
                            } else if (record.target.matches(".navbar-toggler")
                                    && collapseTogglerAttributes.includes(record.attributeName)) {
                                return false;
                            }

                            // Do not record the extra menu changes.
                            if (record.target.matches("#top_menu li, #top_menu li > a")
                                    && record.attributeName === "class") {
                                if (checkForExcludedClasses(record, extraMenuClasses)) {
                                    return false;
                                }
                            }
                        }
                    } else if (record.type === "childList") {
                        const addedOrRemovedNode = record.addedNodes[0] || record.removedNodes[0];
                        // Do not record the addition/removal of the extra menu
                        // and the menus inside it.
                        if (addedOrRemovedNode.nodeType === Node.ELEMENT_NODE
                                && addedOrRemovedNode.matches(".o_extra_menu_items, #top_menu li")) {
                            return false;
                        }
                    }
                    return true;
                });
            },
        });

        return ret;
    },
    /**
     * @override
     * @returns {Promise}
     */
    _saveViewBlocks: async function () {
        await this._super.apply(this, arguments);
        if (this.isDirty()) {
            return this._restoreMegaMenus();
        }
    },
    /**
     * @override
     */
    destroy: function () {
        this._restoreMegaMenus();
        this._super.apply(this, arguments);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * @private
     * @param {HTMLElement} editable
     */
    _saveCoverProperties: function ($elementToSave) {
        var el = $elementToSave.closest('.o_record_cover_container')[0];
        if (!el) {
            return;
        }

        var resModel = el.dataset.resModel;
        var resID = parseInt(el.dataset.resId);
        if (!resModel || !resID) {
            throw new Error('There should be a model and id associated to the cover');
        }

        // The cover might be dirty for another reason than cover properties
        // values only (like an editable text inside). In that case, do not
        // update the cover properties values.
        if (!('coverClass' in el.dataset)) {
            return;
        }

        this.__savedCovers = this.__savedCovers || {};
        this.__savedCovers[resModel] = this.__savedCovers[resModel] || [];

        if (this.__savedCovers[resModel].includes(resID)) {
            return;
        }
        this.__savedCovers[resModel].push(resID);

        var cssBgImage = $(el.querySelector('.o_record_cover_image')).css('background-image');
        var coverProps = {
            'background-image': cssBgImage.replace(/"/g, '').replace(window.location.protocol + "//" + window.location.host, ''),
            'background_color_class': el.dataset.bgColorClass,
            'background_color_style': el.dataset.bgColorStyle,
            'opacity': el.dataset.filterValue,
            'resize_class': el.dataset.coverClass,
            'text_align_class': el.dataset.textAlignClass,
        };

        return this._rpc({
            model: resModel,
            method: 'write',
            args: [
                resID,
                {'cover_properties': JSON.stringify(coverProps)}
            ],
        });
    },
    /**
     * @override
     */
    async _saveElement($el, context, withLang, ...rest) {
        var promises = [];

        // Saving Embed Code snippets with <script> in the database, as these
        // elements are removed in edit mode.
        if ($el[0].querySelector(".s_embed_code")) {
            // Copied so as not to impact the actual DOM and prevent scripts
            // from loading.
            const $clonedEl = $el.clone(true, true);
            for (const embedCodeEl of $clonedEl[0].querySelectorAll(".s_embed_code")) {
                const embedTemplateEl = embedCodeEl.querySelector(".s_embed_code_saved");
                if (embedTemplateEl) {
                    embedCodeEl.querySelector(".s_embed_code_embedded")
                        .replaceChildren(cloneContentEls(embedTemplateEl.content, true));
                }
            }
            await this._super($clonedEl, context, withLang, ...rest);
        } else {
            // Saving a view content
            await this._super.apply(this, arguments);
        }

        // Saving mega menu options
        if ($el.data('oe-field') === 'mega_menu_content') {
            // On top of saving the mega menu content like any other field
            // content, we must save the custom classes that were set on the
            // menu itself.
            // FIXME normally removing the 'show' class should not be necessary here
            // TODO check that editor classes are removed here as well
            var classes = _.without($el.attr('class').split(' '), 'dropdown-menu', 'o_mega_menu', 'show');
            promises.push(this._rpc({
                model: 'website.menu',
                method: 'write',
                args: [
                    [parseInt($el.data('oe-id'))],
                    {
                        'mega_menu_classes': classes.join(' '),
                    },
                ],
            }));
        }

        // Saving cover properties on related model if any
        var prom = this._saveCoverProperties($el);
        if (prom) {
            promises.push(prom);
        }

        return Promise.all(promises);
    },
    /**
     * Restores mega menu behaviors and closes them (important to do before
     * saving otherwise they would be saved opened).
     *
     * @private
     * @returns {Promise}
     */
    _restoreMegaMenus: function () {
        var $megaMenuToggles = this.$('.o_mega_menu_toggle');
        $megaMenuToggles.off('.wysiwyg_megamenu')
            .attr('data-toggle', 'dropdown')
            .dropdown({});
        return toggleDropdown($megaMenuToggles, false);
    },
    /**
     * Toggles the mega menu.
     *
     * @private
     * @returns {Promise}
     */
    _toggleMegaMenu: function (toggleEl) {
        const megaMenuEl = toggleEl.parentElement.querySelector('.o_mega_menu');
        if (!megaMenuEl || !megaMenuEl.classList.contains('show')) {
            return this.snippetsMenu.activateSnippet(false);
        }
        this.odooEditor.observerUnactive("toggleMegaMenu");
        megaMenuEl.classList.add('o_no_parent_editor');
        this.odooEditor.observerActive("toggleMegaMenu");
        return this.snippetsMenu.activateSnippet($(megaMenuEl));
    },
});

snippetsEditor.SnippetsMenu.include({
    /**
     * @override
     */
    init: function () {
        this._super(...arguments);
        this._notActivableElementsSelector += ', .o_mega_menu_toggle';
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * @override
     */
    _insertDropzone: function ($hook) {
        var $hookParent = $hook.parent();
        var $dropzone = this._super(...arguments);
        $dropzone.attr('data-editor-message', $hookParent.attr('data-editor-message'));
        $dropzone.attr('data-editor-sub-message', $hookParent.attr('data-editor-sub-message'));
        return $dropzone;
    },
});
});
