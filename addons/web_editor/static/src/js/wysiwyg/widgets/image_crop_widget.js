odoo.define('wysiwyg.widgets.ImageCropWidget', function (require) {
'use strict';

const core = require('web.core');
const Widget = require('web.Widget');
const {applyModifications, cropperDataFields, activateCropper, loadImage, loadImageInfo} = require('web_editor.image_processing');
const { Markup } = require('web.utils');
const { scrollTo } = require("web.dom");

const _t = core._t;

const ImageCropWidget = Widget.extend({
    template: ['wysiwyg.widgets.crop'],
    xmlDependencies: ['/web_editor/static/src/xml/wysiwyg.xml'],
    events: {
        'click.crop_options [data-action]': '_onCropOptionClick',
        // zoom event is triggered by the cropperjs library when the user zooms.
        'zoom': '_onCropZoom',
    },

    /**
     * @constructor
     */
    init(parent, media) {
        this._super(...arguments);
        this.media = media;
        this.parent = parent;
        this.$media = $(media);
        // Needed for editors in iframes.
        this.document = media.ownerDocument;
        // key: ratio identifier, label: displayed to user, value: used by cropper lib
        this.aspectRatios = {
            "0/0": {label: _t("Flexible"), value: 0},
            "16/9": {label: "16:9", value: 16 / 9},
            "4/3": {label: "4:3", value: 4 / 3},
            "1/1": {label: "1:1", value: 1},
            "2/3": {label: "2:3", value: 2 / 3},
        };
        const src = this.media.getAttribute('src');
        const data = Object.assign({}, media.dataset);
        this.initialSrc = src;
        this.aspectRatio = data.aspectRatio || "0/0";
        this.mimetype = data.mimetype || src.endsWith('.png') ? 'image/png' : 'image/jpeg';
    },
    /**
     * @override
     */
    async willStart() {
        await this._super.apply(this, arguments);
        await loadImageInfo(this.media, this._rpc.bind(this));
        const isIllustration = /^\/web_editor\/shape\/illustration\//.test(this.media.dataset.originalSrc);
        await this._scrollToInvisibleImage();
        if (this.media.dataset.originalSrc && !isIllustration) {
            this.originalSrc = this.media.dataset.originalSrc;
            this.originalId = this.media.dataset.originalId;
            const sel = this.parent.odooEditor && this.parent.odooEditor.document.getSelection();
            sel && sel.removeAllRanges();
            return;
        }
        // Couldn't find an attachment: not croppable.
        this.uncroppable = true;
    },
    /**
     * @override
     */
    async start() {
        if (this.uncroppable) {
            this.displayNotification({
              type: 'warning',
              title: _t("This image is an external image"),
              message: Markup(_t("This type of image is not supported for cropping.<br/>If you want to crop it, please first download it from the original source and upload it in Odoo.")),
            });
            return this.destroy();
        }
        const _super = this._super.bind(this);
        const $cropperWrapper = this.$('.o_we_cropper_wrapper');

        // Replacing the src with the original's so that the layout is correct.
        await loadImage(this.originalSrc, this.media);
        this.$cropperImage = this.$('.o_we_cropper_img');
        const cropperImage = this.$cropperImage[0];
        [cropperImage.style.width, cropperImage.style.height] = [this.$media.width() + 'px', this.$media.height() + 'px'];

        // Overlaying the cropper image over the real image
        const offset = this.$media.offset();
        offset.left += parseInt(this.$media.css('padding-left'));
        offset.top += parseInt(this.$media.css('padding-right'));
        $cropperWrapper.offset(offset);

        await loadImage(this.originalSrc, cropperImage);
        await activateCropper(cropperImage, this.aspectRatios[this.aspectRatio].value, this.media.dataset);

        this._onDocumentMousedown = this._onDocumentMousedown.bind(this);
        this._onDocumentKeydown = this._onDocumentKeydown.bind(this);
        // We use capture so that the handler is called before other editor handlers
        // like save, such that we can restore the src before a save.
        this.document.addEventListener('mousedown', this._onDocumentMousedown, {capture: true});
        this.document.addEventListener('keydown', this._onDocumentKeydown, {capture: true});
        return _super(...arguments);
    },
    /**
     * @override
     */
    destroy() {
        if (this.$cropperImage) {
            this.$cropperImage.cropper('destroy');
            this.document.removeEventListener('mousedown', this._onDocumentMousedown, {capture: true});
            this.document.removeEventListener('keydown', this._onDocumentKeydown, {capture: true});
        }
        this.media.setAttribute('src', this.initialSrc);
        this.$media.trigger('image_cropper_destroyed');
        return this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------

    /**
     * Resets the crop
     */
    async reset() {
        if (this.$cropperImage) {
            this.$cropperImage.cropper('reset');
            if (this.aspectRatio !== '0/0') {
                this.aspectRatio = '0/0';
                this.$cropperImage.cropper('setAspectRatio', this.aspectRatios[this.aspectRatio].value);
            }
            await this._save(false);
        }
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Updates the DOM image with cropped data and associates required
     * information for a potential future save (where required cropped data
     * attachments will be created).
     *
     * @private
     * @param {boolean} [cropped=true]
     */
    async _save(cropped = true) {
        // Mark the media for later creation of cropped attachment
        this.media.classList.add('o_modified_image_to_save');

        [...cropperDataFields, 'aspectRatio'].forEach(attr => {
            delete this.media.dataset[attr];
            const value = this._getAttributeValue(attr);
            if (value) {
                this.media.dataset[attr] = value;
            }
        });
        delete this.media.dataset.resizeWidth;
        this.initialSrc = await applyModifications(this.media);
        this.media.classList.toggle('o_we_image_cropped', cropped);
        this.$media.trigger('image_cropped');
        this.destroy();
    },
    /**
     * Returns an attribute's value for saving.
     *
     * @private
     */
    _getAttributeValue(attr) {
        if (cropperDataFields.includes(attr)) {
            return this.$cropperImage.cropper('getData')[attr];
        }
        return this[attr];
    },
    /**
     * Resets the crop box to prevent it going outside the image.
     *
     * @private
     */
    _resetCropBox() {
        this.$cropperImage.cropper('clear');
        this.$cropperImage.cropper('crop');
    },
    /**
     * Make sure the targeted image is in the visible viewport before crop.
     *
     * @private
     */
    async _scrollToInvisibleImage() {
        const rect = this.media.getBoundingClientRect();
        const viewportTop = this.document.documentElement.scrollTop || 0;
        const viewportBottom = viewportTop + window.innerHeight;
        const closestScrollable = el => {
            if (!el) {
                return null;
            }
            if (el.scrollHeight > el.clientHeight) {
                return $(el);
            } else {
                return closestScrollable(el.parentElement);
            }
        }
        // Give priority to the closest scrollable element (e.g. for images in
        // HTML fields, the element to scroll is different from the document's
        // scrolling element).
        const $scrollable = closestScrollable(this.media);

        // The image must be in a position that allows access to it and its crop
        // options buttons. Otherwise, the crop widget container can be scrolled
        // to allow editing.
        if (rect.top < viewportTop || viewportBottom - rect.bottom < 100) {
            await scrollTo(this.media, {
                easing: "linear",
                duration: 500,
                ...($scrollable && {$scrollable}),
            });
        }
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * Called when a crop option is clicked -> change the crop area accordingly.
     *
     * @private
     * @param {MouseEvent} ev
     */
    _onCropOptionClick(ev) {
        const {action, value, scaleDirection} = ev.currentTarget.dataset;
        switch (action) {
            case 'ratio':
                this.$cropperImage.cropper('reset');
                this.aspectRatio = value;
                this.$cropperImage.cropper('setAspectRatio', this.aspectRatios[this.aspectRatio].value);
                break;
            case 'zoom':
            case 'reset':
                this.$cropperImage.cropper(action, value);
                break;
            case 'rotate':
                this.$cropperImage.cropper(action, value);
                this._resetCropBox();
                break;
            case 'flip': {
                const amount = this.$cropperImage.cropper('getData')[scaleDirection] * -1;
                return this.$cropperImage.cropper(scaleDirection, amount);
            }
            case 'apply':
                return this._save();
            case 'discard':
                return this.destroy();
        }
    },
    /**
     * Discards crop if the user clicks outside of the widget.
     *
     * @private
     * @param {MouseEvent} ev
     */
    _onDocumentMousedown(ev) {
        if (document.body.contains(ev.target) && this.$(ev.target).length === 0) {
            return this.destroy();
        }
    },
    /**
     * Resets the cropbox on zoom to prevent crop box overflowing.
     *
     * @private
     */
    async _onCropZoom() {
        // Wait for the zoom event to be fully processed before reseting.
        await new Promise(res => setTimeout(res, 0));
        this._resetCropBox();
    },
    /**
     * Save crop if user hits enter.
     * @private
     * @param {KeyboardEvent} ev
     */
    _onDocumentKeydown(ev) {
        if(ev.key === 'Enter') {
            return this._save();
        }
    }
});

return ImageCropWidget;
});
