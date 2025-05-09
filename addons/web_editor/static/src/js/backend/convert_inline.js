/** @odoo-module alias=web_editor.convertInline */
'use strict';

import FieldHtml from 'web_editor.field.html';
import { isBlock, rgbToHex } from '../../../lib/odoo-editor/src/utils/utils';

//--------------------------------------------------------------------------
// Constants
//--------------------------------------------------------------------------

const RE_COL_MATCH = /(^| )col(-[\w\d]+)*( |$)/;
const RE_COMMAS_OUTSIDE_PARENTHESES = /,(?![^(]*?\))/g;
const RE_OFFSET_MATCH = /(^| )offset(-[\w\d]+)*( |$)/;
const RE_PADDING = /([\d.]+)/;
const RE_WHITESPACE = /[\s\u200b]*/;
const SELECTORS_IGNORE = /(^\*$|:hover|:before|:after|:active|:link|::|'|\([^(),]+[,(])/;
// Attributes all tables should have in a mailing.
const TABLE_ATTRIBUTES = {
    cellspacing: 0,
    cellpadding: 0,
    border: 0,
    width: '100%',
    align: 'center',
    role: 'presentation',
};
// Cancel tables default styles.
const TABLE_STYLES = {
    'border-collapse': 'collapse',
    'text-align': 'inherit',
    'font-size': 'unset',
    'line-height': 'unset',
};

//--------------------------------------------------------------------------
// Public
//--------------------------------------------------------------------------

/**
 * Convert snippets and mailing bodies to tables.
 *
 * @param {JQuery} $editable
 */
function addTables($editable) {
    const editable = $editable.get(0);
    for (const snippet of editable.querySelectorAll('.o_mail_snippet_general, .o_layout')) {
        // Convert all snippets and the mailing itself into table > tr > td
        const table = _createTable(snippet.attributes);

        const row = document.createElement('tr');
        let col = document.createElement('td');
        row.appendChild(col);
        if (snippet.classList.contains('o_basic_theme')) {
            const div = document.createElement('div');
            div.classList.add('o_apple_wrapper_padding');
            col.appendChild(div);
            col = div;
            const style = document.createElement('style');
            // We create a nested media query because it's only supported by a
            // handful of clients, including Apple Mail, and we actually only
            // want this for Apple Mail.
            const padding = '34px'; // This is what's needed to align the content with Apple Mail's header.
            style.textContent = `@media{@media{.o_basic_theme div.o_apple_wrapper_padding{padding:${snippet.style.padding};}}}` +
                `@media(min-width:961px){@media{@media{.o_basic_theme div.o_apple_wrapper_padding{padding-left:${padding};}}}}`;
            div.before(style);
        }
        table.appendChild(row);

        for (const child of [...snippet.childNodes]) {
            col.appendChild(child);
        }
        snippet.before(table);
        snippet.remove();

        // If snippet doesn't have a table as child, wrap its contents in one.
        const childTables = [...col.children].filter(child => child.nodeName === 'TABLE');
        if (!childTables.length) {
            const tableB = _createTable();
            const rowB = document.createElement('tr');
            const colB = document.createElement('td');

            rowB.appendChild(colB);
            tableB.appendChild(rowB);
            for (const child of [...col.childNodes]) {
                colB.appendChild(child);
            }
            col.appendChild(tableB);
        }
    }
}
/**
 * Convert CSS display for attachment link to real image.
 * Without this post process, the display depends on the CSS and the picture
 * does not appear when we use the html without css (to send by email for e.g.)
 *
 * @param {JQuery} $editable
 */
function attachmentThumbnailToLinkImg($editable) {
    const editable = $editable.get(0);
    const links = [...editable.querySelectorAll(`a[href*="/web/content/"][data-mimetype]:empty`)].filter(link => (
        RE_WHITESPACE.test(link.textContent)
    ));
    for (const link of links) {
        const image = document.createElement('img');
        image.setAttribute('src', _getStylePropertyValue(link, 'background-image').replace(/(^url\(['"])|(['"]\)$)/g, ''));
        // Note: will trigger layout thrashing.
        image.setAttribute('height', Math.max(1, _getHeight(link)));
        image.setAttribute('width', Math.max(1, _getWidth(link)));
        link.prepend(image);
    };
}
/**
 * Convert Bootstrap rows and columns to actual tables.
 *
 * Note: Because of the limited support of media queries in emails, this doesn't
 * support the mixing and matching of column options (e.g., "col-4 col-sm-6" and
 * "col col-4" aren't supported).
 *
 * @param {JQuery} $editable
 */
function bootstrapToTable($editable) {
    const editable = $editable.get(0);
    // First give all rows in columns a separate container parent.
    for (const rowInColumn of [...editable.querySelectorAll('.row')].filter(row => RE_COL_MATCH.test(row.parentElement.className))) {
        const parentColumn = rowInColumn.parentElement;
        const previous = rowInColumn.previousElementSibling;
        if (previous && previous.classList.contains('o_fake_table')) {
            // If a container was already created there, append to it.
            previous.append(rowInColumn);
        } else {
            _wrap(rowInColumn, 'div', 'o_fake_table');
        }
        // Bootstrap rows have negative left and right margins, which are not
        // supported by GMail and Outlook. Add up the padding of the column with
        // the negative margin of the row to get the correct padding.
        const rowStyle = getComputedStyle(rowInColumn);
        const columnStyle = getComputedStyle(parentColumn);
        for (const side of ['left', 'right']) {
            const negativeMargin = +rowStyle[`margin-${side}`].replace('px', '');
            const columnPadding = +columnStyle[`padding-${side}`].replace('px', '');
            if (negativeMargin < 0 && columnPadding >= Math.abs(negativeMargin)) {
                parentColumn.style[`padding-${side}`] = `${columnPadding + negativeMargin}px`;
                rowInColumn.style[`margin-${side}`] = 0;
            }
        }
    }

    // These containers from the mass mailing masonry snippet require full
    // height contents, which is only possible if the table itself has a set
    // height. We also need to restyle it because of the change in structure.
    for(const masonryTopInnerContainer of editable.querySelectorAll('.s_masonry_block > .container')) {
        masonryTopInnerContainer.style.setProperty('height', '100%');
    }
    for (const masonryGrid of editable.querySelectorAll('.o_masonry_grid_container')) {
        masonryGrid.style.setProperty('padding', 0);
        for (const fakeTable of [...masonryGrid.children].filter(c => c.classList.contains('o_fake_table'))) {
            fakeTable.style.setProperty('height', _getHeight(fakeTable) + 'px');
        }
    }
    for (const masonryRow of editable.querySelectorAll('.o_masonry_grid_container > .o_fake_table > .row.h-100')) {
        masonryRow.style.removeProperty('height');
        masonryRow.parentElement.style.setProperty('height', '100%');
    }

    // Now convert all containers with rows to tables.
    for (const container of [...editable.querySelectorAll('.container, .container-fluid, .o_fake_table')].filter(n => [...n.children].some(c => c.classList.contains('row')))) {
        // TABLE
        const table = _createTable(container.attributes);
        for (const child of [...container.childNodes]) {
            table.append(child);
        }
        table.classList.remove('container', 'container-fluid', 'o_fake_table');
        if (!table.className) {
            table.removeAttribute('class');
        }
        container.before(table);
        container.remove();


        // ROWS
        // First give all siblings of rows a separate row/col parent combo.
        for (const row of [...table.children].filter(child => isBlock(child) && !child.classList.contains('row'))) {
            const newCol = _wrap(row, 'div', 'col-12');
            _wrap(newCol, 'div', 'row');
        }

        for (const bootstrapRow of [...table.children].filter(c => c.classList.contains('row'))) {
            const tr = document.createElement('tr');
            for (const attr of bootstrapRow.attributes) {
                tr.setAttribute(attr.name, attr.value);
            }
            tr.classList.remove('row');
            if (!tr.className) {
                tr.removeAttribute('class');
            }
            for (const child of [...bootstrapRow.childNodes]) {
                tr.append(child);
            }
            bootstrapRow.before(tr);
            bootstrapRow.remove();


            // COLUMNS
            const bootstrapColumns = [...tr.children].filter(column => column.className && column.className.match(RE_COL_MATCH));

            // 1. Replace generic "col" classes with specific "col-n", computed
            //    by sharing the available space between them.
            const flexColumns = bootstrapColumns.filter(column => !/\d/.test(column.className.match(RE_COL_MATCH)[0] || '0'));
            const colTotalSize = bootstrapColumns.map(child => _getColumnSize(child) + _getColumnOffsetSize(child)).reduce((a, b) => a + b, 0);
            const colSize = Math.max(1, Math.round((12 - colTotalSize) / flexColumns.length));
            for (const flexColumn of flexColumns) {
                flexColumn.classList.remove(flexColumn.className.match(RE_COL_MATCH)[0].trim());
                flexColumn.classList.add(`col-${colSize}`);
            }

            // 2. Create and fill up the row(s) with grid(s).
            // Create new, empty columns for column offsets.
            let columnIndex = 0;
            for (const bootstrapColumn of [...bootstrapColumns]) {
                const offsetSize = _getColumnOffsetSize(bootstrapColumn);
                if (offsetSize) {
                    const newColumn = document.createElement('div');
                    newColumn.classList.add(`col-${offsetSize}`);
                    bootstrapColumn.classList.remove(bootstrapColumn.className.match(RE_OFFSET_MATCH)[0].trim());
                    bootstrapColumn.before(newColumn);
                    bootstrapColumns.splice(columnIndex, 0, newColumn);
                    columnIndex++;
                }
                columnIndex++;
            }
            let grid = _createColumnGrid();
            let gridIndex = 0;
            let currentRow = tr.cloneNode();
            tr.after(currentRow);
            let currentCol;
            columnIndex = 0;
            for (const bootstrapColumn of bootstrapColumns) {
                const columnSize = _getColumnSize(bootstrapColumn);
                if (gridIndex + columnSize < 12) {
                    currentCol = grid[gridIndex];
                    _applyColspan(currentCol, columnSize);
                    gridIndex += columnSize;
                    if (columnIndex === bootstrapColumns.length - 1) {
                        // We handled all the columns but there is still space
                        // in the row. Insert the columns and fill the row.
                        _applyColspan(grid[gridIndex], 12 - gridIndex);
                        currentRow.append(...grid.filter(td => td.getAttribute('colspan')));
                    }
                } else if (gridIndex + columnSize === 12) {
                    // Finish the row.
                    currentCol = grid[gridIndex];
                    _applyColspan(currentCol, columnSize);
                    currentRow.append(...grid.filter(td => td.getAttribute('colspan')));
                    if (columnIndex !== bootstrapColumns.length - 1) {
                        // The row was filled before we handled all of its
                        // columns. Create a new one and start again from there.
                        const previousRow = currentRow;
                        currentRow = currentRow.cloneNode();
                        previousRow.after(currentRow);
                        grid = _createColumnGrid();
                        gridIndex = 0;
                    }
                } else {
                    // Fill the row with what was in the grid before it
                    // overflowed.
                    _applyColspan(grid[gridIndex], 12 - gridIndex);
                    currentRow.append(...grid.filter(td => td.getAttribute('colspan')));
                    // Start a new row that starts with the current col.
                    const previousRow = currentRow;
                    currentRow = currentRow.cloneNode();
                    previousRow.after(currentRow);
                    grid = _createColumnGrid();
                    currentCol = grid[0];
                    _applyColspan(currentCol, columnSize);
                    gridIndex = columnSize;
                    if (columnIndex === bootstrapColumns.length - 1 && gridIndex < 12) {
                        // We handled all the columns but there is still space
                        // in the row. Insert the columns and fill the row.
                        _applyColspan(grid[gridIndex], 12 - gridIndex);
                        currentRow.append(...grid.filter(td => td.getAttribute('colspan')));
                    }
                }
                if (currentCol) {
                    for (const attr of bootstrapColumn.attributes) {
                        if (attr.name !== 'colspan') {
                            currentCol.setAttribute(attr.name, attr.value);
                        }
                    }
                    const colMatch = bootstrapColumn.className.match(RE_COL_MATCH);
                    currentCol.classList.remove(colMatch[0].trim());
                    if (!currentCol.className) {
                        currentCol.removeAttribute('class');
                    }
                    for (const child of [...bootstrapColumn.childNodes]) {
                        currentCol.append(child);
                    }
                    // Adapt width to colspan.
                    _applyColspan(currentCol, +currentCol.getAttribute('colspan'));
                }
                columnIndex++;
            }
            tr.remove(); // row was cloned and inserted already
        }
        // Merge tables in tds into one common table, each in its own row.
        const tds = [...editable.querySelectorAll('td')]
            .filter(td => td.children.length > 1 && [...td.children].every(child => child.nodeName === 'TABLE'))
            .reverse();
        for (const td of tds) {
            const table = _createTable();
            const trs = [...td.children].map(child => _wrap(child, 'td')).map(wrappedChild => _wrap(wrappedChild, 'tr'));
            trs[0].before(table);
            table.append(...trs);
        }
    }
}
/**
 * Convert Bootstrap cards to table structures.
 *
 * @param {JQuery} $editable
 */
function cardToTable($editable) {
    const editable = $editable.get(0);
    for (const card of editable.querySelectorAll('.card')) {
        const table = _createTable(card.attributes);
        table.style.removeProperty('overflow');
        const cardImgTopSuperRows = [];
        for (const child of [...card.childNodes]) {
            const row = document.createElement('tr');
            const col = document.createElement('td');
            if (!['IMG', 'A'].includes(child.nodeName) && isBlock(child)) {
                for (const attr of child.attributes) {
                    col.setAttribute(attr.name, attr.value);
                }
                for (const descendant of [...child.childNodes]) {
                    col.append(descendant);
                }
                child.remove();
            } else if (child.nodeType === Node.TEXT_NODE) {
                if (child.textContent.replace(RE_WHITESPACE, '').length) {
                    col.append(child);
                } else {
                    continue;
                }
            } else {
                col.append(child);
            }
            const subTable = _createTable();
            const superRow = document.createElement('tr');
            const superCol = document.createElement('td');
            row.append(col);
            subTable.append(row);
            superCol.append(subTable);
            superRow.append(superCol);
            table.append(superRow);
            if (child.nodeType === Node.ELEMENT_NODE) {
                const hasImgTop = [child, ...child.querySelectorAll('.card-img-top')].some(node => (
                    node.classList && node.classList.contains('card-img-top') && node.closest && node.closest('.card') === table
                ));
                if (hasImgTop) {
                    // Collect .card-img-top superRows to manipulate their heights.
                    cardImgTopSuperRows.push(superRow);
                }
            }
        }
        // We expect successive .card-img-top to have the same height so the
        // bodies of the cards are aligned. This achieves that without flexboxes
        // by forcing the height of the smallest card:
        const smallestCardImgRow = Math.min(0, ...cardImgTopSuperRows.map(row => row.clientHeight));
        for (const row of cardImgTopSuperRows) {
            row.style.height = smallestCardImgRow + 'px';
        }
        card.before(table);
        card.remove();
    }
}
/**
 * Convert CSS style to inline style (leave the classes on elements but forces
 * the style they give as inline style).
 *
 * @param {JQuery} $editable
 * @param {Object} cssRules
 */
function classToStyle($editable, cssRules) {
    const editable = $editable.get(0);
    const writes = [];
    const nodeToRules = new Map();
    const rulesToProcess = [];
    for (const rule of cssRules) {
        const nodes = editable.querySelectorAll(rule.selector);
        if (nodes.length) {
            rulesToProcess.push(rule);
        }
        for (const node of nodes) {
            const nodeRules = nodeToRules.get(node);
            if (!nodeRules) {
                nodeToRules.set(node, [rule]);
            } else {
                nodeRules.push(rule);
            }
        }
    }
    _computeStyleAndSpecificityOnRules(rulesToProcess);
    for (const rules of nodeToRules.values()) {
        rules.sort((a, b) => a.specificity - b.specificity);
    }

    for (const node of nodeToRules.keys()) {
        const nodeRules = nodeToRules.get(node);
        const css = nodeRules ? _getMatchedCSSRules(node, nodeRules) : {};
        // Flexbox
        for (const styleName of node.style) {
            if (styleName.includes('flex') || `${node.style[styleName]}`.includes('flex')) {
                writes.push(() => { node.style[styleName] = ''; });
            }
        }
        // Ignore font-family (mail-safe font declared in <head>)
        if ('font-family' in css) {
            delete css['font-family'];
        }

        // Do not apply css that would override inline styles (which are prioritary).
        let style = node.getAttribute('style') || '';
        // Outlook doesn't support inline !important
        style = style.replace(/!important/g,'');
        for (const [key, value] of Object.entries(css)) {
            if (!(new RegExp(`(^|;)\\s*${key}`).test(style))) {
                style = `${key}:${value};${style}`;
            }
        };
        if (_.isEmpty(style)) {
            writes.push(() => { node.removeAttribute('style'); });
        } else {
            writes.push(() => {
                node.setAttribute('style', style);
                if (node.style.width) {
                    node.setAttribute('width', ('' + node.style.width).replace('px', ''));
                }
            });
        }

        // Media list images should not have an inline height
        if (node.nodeName === 'IMG' && node.classList.contains('s_media_list_img')) {
            writes.push(() => { node.style.removeProperty('height'); });
        }
        // Apple Mail
        if (node.nodeName === 'TD' && !node.childNodes.length) {
            writes.push(() => { node.appendChild(document.createTextNode('&nbsp;')); });
        }
        // Outlook
        if (node.nodeName === 'A' && node.classList.contains('btn') && !node.classList.contains('btn-link') && !node.children.length) {
            writes.push(() => { node.prepend(document.createComment('[if mso]><i style="letter-spacing: 25px; mso-font-width: -100%; mso-text-raise: 30pt;">&nbsp;</i><![endif]')); });
            writes.push(() => { node.append(document.createComment('[if mso]><i style="letter-spacing: 25px; mso-font-width: -100%;">&nbsp;</i><![endif]')); });
        } else if (node.nodeName === 'IMG' && node.classList.contains('mx-auto') && node.classList.contains('d-block')) {
            writes.push(() => { _wrap(node, 'p', 'o_outlook_hack', 'text-align:center;margin:0'); });
        }
    };
    writes.forEach(fn => fn());
}
/**
 * Convert the contents of an editable area (as a JQuery element) into content
 * that is widely compatible with email clients. If no CSS Rules are given, they
 * will be computed for the editable element's owner document.
 *
 * @param {JQuery} $editable
 * @param {Object[]} [cssRules] Array<{selector: string;
 *                                   style: {[styleName]: string};
 *                                   specificity: number;}>
 * @param {JQuery} [$iframe] the iframe containing the editable, if any
 */
function toInline($editable, cssRules, $iframe) {
    $editable.removeClass('odoo-editor-editable');
    const editable = $editable.get(0);
    const iframe = $iframe && $iframe.get(0);
    const doc = editable.ownerDocument;
    cssRules = cssRules || doc._rulesCache;
    if (!cssRules) {
        cssRules = getCSSRules(doc);
        doc._rulesCache = cssRules;
    }

    // If the editable is not visible, we need to make it visible in order to
    // retrieve image/icon dimensions. This iterates over ancestors to make them
    // visible again. We then restore it at the end of this function.
    const displaysToRestore = [];
    if (_isHidden(editable)) {
        let ancestor = editable;
        while (ancestor && ancestor.nodeName !== 'html' && _isHidden(ancestor)) {
            if (_getStylePropertyValue(ancestor, 'display') === 'none') {
                displaysToRestore.push([ancestor, ancestor.style.display]);
                ancestor.style.setProperty('display', 'block');
            }
            ancestor = ancestor.parentElement;
            if ((!ancestor || ancestor.nodeName === 'HTML') && iframe) {
                ancestor = iframe;
            }
        }
    }
    // Fix card-img-top heights (must happen before we transform everything).
    for (const imgTop of editable.querySelectorAll('.card-img-top')) {
        imgTop.style.setProperty('height', _getHeight(imgTop) + 'px');
    }
    // Flag img-fluid images with fixed width/height for later.
    for (const imgFluid of editable.querySelectorAll('.img-fluid')) {
        if (!Number.isNaN(+imgFluid.style.width.replace('px', ''))) {
            imgFluid.classList.add('o_img_fluid_fixed_width');
        }
        if (!Number.isNaN(+imgFluid.style.height.replace('px', ''))) {
            imgFluid.classList.add('o_img_fluid_fixed_height');
        }
    }
    // Fix Outlook image rendering bug.
    for (const attributeName of ['width', 'height']) {
        const images = editable.querySelectorAll('img');
        for (const image of images) {
            let value = image.getAttribute(attributeName) || (attributeName === 'height' && image.offsetHeight);
            if (!value) {
                value = attributeName === 'width' ? _getWidth(image) : _getHeight(image);;
            }
            image.setAttribute(attributeName, ('' + value).replace('px', ''));
        };
    };

    attachmentThumbnailToLinkImg($editable);
    fontToImg($editable);
    classToStyle($editable, cssRules);
    bootstrapToTable($editable);
    cardToTable($editable);
    listGroupToTable($editable);
    addTables($editable);
    formatTables($editable);
    normalizeColors($editable);
    const rootFontSizeProperty = getComputedStyle(editable.ownerDocument.documentElement).fontSize;
    const rootFontSize = parseFloat(rootFontSizeProperty.replace(/[^\d\.]/g, ''));
    normalizeRem($editable, rootFontSize);

    // Fix mx-auto on images in table cells.
    for (const centeredImage of editable.querySelectorAll('td > img.mx-auto')) {
        if (centeredImage.parentElement.children.length === 1) {
            centeredImage.parentElement.style.setProperty('text-align', 'center');
        }
    }
    // Ensure preservation of aspect-ratio.
    for (const loneImage of editable.querySelectorAll('img:only-child:not(.img-fluid,[data-class*=fa-])')) {
        loneImage.style.setProperty('object-fit', 'cover');
    }
    // Fix img-fluid.
    for (const image of editable.querySelectorAll('img.img-fluid')) {
        // Outlook requires absolute width/height.
        const clone = image.cloneNode();
        const width = _getWidth(image);
        clone.setAttribute('width', width);
        clone.style.setProperty('width', width + 'px');
        clone.style.removeProperty('max-width');
        const height = _getHeight(image);
        clone.setAttribute('height', height);
        clone.style.setProperty('height', height + 'px');
        clone.style.removeProperty('max-height');
        image.before(document.createComment(`[if mso]>${clone.outerHTML}<![endif]`));
        image.setAttribute('style', `${image.getAttribute('style') || ''} mso-hide: all;`.trim());
        image.before(document.createComment('[if !mso]><!'));
        image.after(document.createComment('<![endif]'));
        // Account for the absence of responsive stacking (let max-width do the
        // resizing work outside of Outlook).
        if (!image.style.width.endsWith('%') && !image.classList.contains('o_img_fluid_fixed_width')) {
            image.removeAttribute('width');
            image.style.removeProperty('width');
        }
        if (!image.style.height.endsWith('%') && !image.classList.contains('o_img_fluid_fixed_height')) {
            image.removeAttribute('height');
            image.style.removeProperty('height');
        }
        image.classList.remove('o_img_fluid_fixed_width', 'o_img_fluid_fixed_height');
    }

    for (const [node, displayValue] of displaysToRestore) {
        node.style.setProperty('display', displayValue);
    }
    $editable.addClass('odoo-editor-editable');
}
/**
 * Convert font icons to images.
 *
 * @param {JQuery} $editable - the element in which the font icons have to be
 *                           converted to images
 */
function fontToImg($editable) {
    const editable = $editable.get(0);
    const fonts = odoo.__DEBUG__.services["wysiwyg.fonts"];

    for (const font of editable.querySelectorAll('.fa')) {
        let icon, content;
        fonts.fontIcons.find(fontIcon => {
            return fonts.getCssSelectors(fontIcon.parser).find(data => {
                if (font.matches(data.selector.replace(/::?before/g, ''))) {
                    icon = data.names[0].split('-').shift();
                    content = data.css.match(/content:\s*['"]?(.)['"]?/)[1];
                    return true;
                }
            });
        });
        if (content) {
            const color = _getStylePropertyValue(font, 'color').replace(/\s/g, '');
            let backgroundColoredElement = font;
            let bg, isTransparent;
            do {
                bg = _getStylePropertyValue(backgroundColoredElement, 'background-color').replace(/\s/g, '');
                isTransparent = bg === 'transparent' || bg === 'rgba(0,0,0,0)';
                backgroundColoredElement = backgroundColoredElement.parentElement;
            } while (isTransparent && backgroundColoredElement);
            if (bg === 'rgba(0,0,0,0)' && isTransparent) {
                // default on white rather than black background since opacity
                // is not supported.
                bg = 'rgb(255,255,255)';
            }
            const style = font.getAttribute('style');
            const width = _getWidth(font);
            const height = _getHeight(font);
            const lineHeight = _getStylePropertyValue(font, 'line-height');
            // Compute the padding.
            // First get the dimensions of the icon itself (::before)
            font.style.setProperty('height', 'fit-content');
            font.style.setProperty('width', 'fit-content');
            font.style.setProperty('line-height', 'normal');
            const intrinsicWidth = _getWidth(font);
            const intrinsicHeight = _getHeight(font);
            const hPadding = width && (width - intrinsicWidth) / 2;
            const vPadding = height && (height - intrinsicHeight) / 2;
            let padding = '';
            if (hPadding || vPadding) {
                padding = vPadding ? vPadding + 'px ' : '0 ';
                padding += hPadding ? hPadding + 'px' : '0';
            }
            const image = document.createElement('img');
            image.setAttribute('width', width);
            image.setAttribute('height', height);
            image.setAttribute('src', `/web_editor/font_to_img/${content.charCodeAt(0)}/${encodeURIComponent(color)}/${encodeURIComponent(bg)}/${Math.max(1, Math.round(intrinsicWidth))}x${Math.max(1, Math.round(intrinsicHeight))}`);
            image.setAttribute('data-class', font.getAttribute('class'));
            image.setAttribute('data-style', style);
            image.setAttribute('style', style);
            image.style.setProperty('box-sizing', 'border-box'); // keep the fontawesome's dimensions
            image.style.setProperty('line-height', lineHeight);
            image.style.setProperty('width', intrinsicWidth + 'px');
            image.style.setProperty('height', intrinsicHeight + 'px');
            image.style.setProperty('vertical-align', 'unset'); // undo Bootstrap's default (middle).
            if (!padding) {
                image.style.setProperty('margin', _getStylePropertyValue(font, 'margin'));
            }
            // For rounded images, apply the rounded border to a wrapper, make
            // sure it doesn't get applied to the image itself so the image
            // doesn't get cropped in the process.
            const wrapper = document.createElement('span');
            wrapper.style.setProperty('display', 'inline-block');
            wrapper.append(image);
            font.before(wrapper);
            if (font.classList.contains('mx-auto')) {
                wrapper.parentElement.style.textAlign = 'center';
            }
            font.remove();
            wrapper.style.setProperty('padding', padding);
            const wrapperWidth = width + ['left', 'right'].reduce((sum, side) => (
                sum + (+_getStylePropertyValue(image, `margin-${side}`).replace('px', '') || 0)
            ), 0);
            wrapper.style.setProperty('width', wrapperWidth + 'px');
            wrapper.style.setProperty('height', height + 'px');
            wrapper.style.setProperty('vertical-align', 'text-bottom');
            wrapper.style.setProperty('background-color', image.style.backgroundColor);
            wrapper.setAttribute('class', font.getAttribute('class').replace(new RegExp('(^|\\s+)' + icon + '(-[^\\s]+)?', 'gi'), '')); // remove inline font-awsome style);
        } else {
            font.remove();
        }
    }
}
/**
 * Format table styles so they display well in most mail clients. This implies
 * moving table paddings to its cells, adding tbody (with canceled styles) where
 * needed, and adding pixel heights to parents of elements with percent heights.
 *
 * @param {JQuery} $editable
 */
function formatTables($editable) {
    const editable = $editable.get(0);
    const writes = [];
    for (const table of editable.querySelectorAll('table.o_mail_snippet_general, .o_mail_snippet_general table')) {
        const tablePaddingTop = parseFloat(_getStylePropertyValue(table, 'padding-top').match(RE_PADDING)[1]);
        const tablePaddingRight = parseFloat(_getStylePropertyValue(table, 'padding-right').match(RE_PADDING)[1]);
        const tablePaddingBottom = parseFloat(_getStylePropertyValue(table, 'padding-bottom').match(RE_PADDING)[1]);
        const tablePaddingLeft = parseFloat(_getStylePropertyValue(table, 'padding-left').match(RE_PADDING)[1]);
        const rows = [...table.querySelectorAll('tr')].filter(tr => tr.closest('table') === table);
        const columns = [...table.querySelectorAll('td')].filter(td => td.closest('table') === table);
        for (const column of columns) {
            const columnsInRow = [...column.closest('tr').querySelectorAll('td')].filter(td => td.closest('table') === table);
            const columnIndex = columnsInRow.findIndex(col => col === column);
            const rowIndex = rows.findIndex(row => row === column.closest('tr'));

            if (!rowIndex) {
                const match = _getStylePropertyValue(column, 'padding-top').match(RE_PADDING);
                const columnPaddingTop = match ? parseFloat(match[1]) : 0;
                writes.push(() => {column.style['padding-top'] = `${columnPaddingTop + tablePaddingTop}px`; });
            }
            if (columnIndex === columnsInRow.length - 1) {
                const match = _getStylePropertyValue(column, 'padding-right').match(RE_PADDING);
                const columnPaddingRight = match ? parseFloat(match[1]) : 0;
                writes.push(() => {column.style['padding-right'] = `${columnPaddingRight + tablePaddingRight}px`; });
            }
            if (rowIndex === rows.length - 1) {
                const match = _getStylePropertyValue(column, 'padding-bottom').match(RE_PADDING);
                const columnPaddingBottom = match ? parseFloat(match[1]) : 0;
                writes.push(() => {column.style['padding-bottom'] = `${columnPaddingBottom + tablePaddingBottom}px`; });
            }
            if (!columnIndex) {
                const match = _getStylePropertyValue(column, 'padding-left').match(RE_PADDING);
                const columnPaddingLeft = match ? parseFloat(match[1]) : 0;
                writes.push(() => {column.style['padding-left'] = `${columnPaddingLeft + tablePaddingLeft}px`; });
            }
        }
        writes.push(() => { table.style.removeProperty('padding'); });
    }
    writes.forEach((fn) => fn());
    // Ensure a tbody in every table and cancel its default style.
    for (const table of [...editable.querySelectorAll('table')].filter(n => ![...n.children].some(c => c.nodeName === 'TBODY'))) {
        const contents = [...table.childNodes];
        const tbody = document.createElement('tbody');
        tbody.style.setProperty('vertical-align', 'top');
        table.prepend(tbody);
        tbody.append(...contents);
    }
    // Children will only take 100% height if the parent has a height property.
    for (const node of [...editable.querySelectorAll('*')].filter(n => (
        n.style && n.style.getPropertyValue('height') === '100%' && (
            !n.parentElement.style.getPropertyValue('height') ||
            n.parentElement.style.getPropertyValue('height').includes('%'))
    ))) {
        let parent = node.parentElement;
        let height = parent.style.getPropertyValue('height');
        while (parent && height && height.includes('%')) {
            parent = parent.parentElement;
            height = parent.style.getPropertyValue('height');
        }
        if (parent) {
            parent.style.setProperty('height', $(parent).height());
        }
    }
    // Align self and justify content don't work on table cells.
    for (const cell of editable.querySelectorAll('td')) {
        const alignSelf = cell.style.alignSelf;
        const justifyContent = cell.style.justifyContent;
        if (alignSelf === 'start' || justifyContent === 'start' || justifyContent === 'flex-start') {
            cell.style.verticalAlign = 'top';
        } else if (alignSelf === 'center' || justifyContent === 'center') {
            cell.style.verticalAlign = 'middle';
        } else if (alignSelf === 'end' || justifyContent === 'end' || justifyContent === 'flex-end') {
            cell.style.verticalAlign = 'bottom';
        }
    }
    // Align items doesn't work on table rows.
    for (const row of editable.querySelectorAll('tr')) {
        const alignItems = row.style.alignItems;
        if (alignItems === 'flex-start') {
            row.style.verticalAlign = 'top';
        } else if (alignItems === 'center') {
            row.style.verticalAlign = 'middle';
        } else if (alignItems === 'flex-end' || alignItems === 'baseline') {
            row.style.verticalAlign = 'bottom';
        } else if (alignItems === 'stretch') {
            const columns = [...row.children].filter(child => child.nodeName === 'TD');
            const biggestHeight = Math.max(...columns.map(column => column.clientHeight));
            for (const column of columns) {
                column.style.height = biggestHeight + 'px';
            }
        }
    }
}
/**
 * Parse through the given document's stylesheets, preprocess(*) them and return
 * the result as an array of objects, each containing a selector string , a
 * style object and a specificity number. Preprocessing involves grouping
 * whatever rules can be grouped together and precomputing their specificity so
 * as to sort them appropriately.
 *
 * @param {Document} doc
 * @returns {Object[]} Array<{selector: string;
 *                            style: {[styleName]: string};
 *                            specificity: number;}>
 */
function getCSSRules(doc) {
    const cssRules = [];
    for (const sheet of doc.styleSheets) {
        // try...catch because browser may not able to enumerate rules for cross-domain sheets
        let rules;
        try {
            rules = sheet.rules || sheet.cssRules;
        } catch (e) {
            console.log("Can't read the css rules of: " + sheet.href, e);
            continue;
        }
        for (const rule of (rules || [])) {
            const subRules = [rule];
            const conditionText = rule.conditionText;
            const minWidthMatch = conditionText && conditionText.match(/\(min-width *: *(\d+)/);
            const minWidth = minWidthMatch && +(minWidthMatch[1] || '0');
            if (minWidth && minWidth >= 992) {
                // Large min-width media queries should be included.
                // eg., .container has a default max-width for all screens.
                let mediaRules;
                try {
                    mediaRules = rule.rules || rule.cssRules;
                    subRules.push(...mediaRules);
                } catch (e) {
                    console.log(`Can't read the css rules of: ${sheet.href} (${conditionText})`, e);
                }
            }
            for (const subRule of subRules) {
                const selectorText = subRule.selectorText || '';
                // Split selectors, making sure not to split at commas in parentheses.
                for (const selector of selectorText.split(RE_COMMAS_OUTSIDE_PARENTHESES)) {
                    if (selector && !SELECTORS_IGNORE.test(selector)) {
                        cssRules.push({ selector: selector.trim(), rawRule: subRule });
                        if (selector === 'body') {
                            // The top element of a mailing has the class
                            // 'o_layout'. Give it the body's styles so they can
                            // trickle down.
                            cssRules.push({ selector: '.o_layout', rawRule: subRule, specificity: 1 });
                        }
                    }
                }
            }
        }
    }

    return cssRules;
}
/**
 * Convert Bootstrap list groups and their items to table structures.
 *
 * @param {JQuery} $editable
 */
function listGroupToTable($editable) {
    const editable = $editable.get(0);
    for (const listGroup of editable.querySelectorAll('.list-group')) {
        let table;
        if (listGroup.querySelectorAll('.list-group-item').length) {
            table = _createTable(listGroup.attributes);
        } else {
            table = listGroup.cloneNode();
            for (const attr of listGroup.attributes) {
                table.setAttribute(attr.name, attr.value);
            }
        }
        for (const child of [...listGroup.childNodes]) {
            if (child.classList && child.classList.contains('list-group-item')) {
                // List groups are <ul>s that render like tables. Their
                // li.list-group-item children should translate to tr > td.
                const row = document.createElement('tr');
                const col = document.createElement('td');
                for (const attr of child.attributes) {
                    col.setAttribute(attr.name, attr.value);
                }
                col.append(...child.childNodes);
                col.classList.remove('list-group-item');
                if (!col.className) {
                    col.removeAttribute('class');
                }
                row.append(col);
                table.append(row);
                child.remove();
            } else if (child.nodeName === 'LI') {
                table.append(...child.childNodes);
            } else {
                table.append(child);
            }
        }
        table.classList.remove('list-group');
        if (!table.className) {
            table.removeAttribute('class');
        }
        if (listGroup.nodeName === 'TD') {
            listGroup.append(table);
            listGroup.classList.remove('list-group');
            if (!listGroup.className) {
                listGroup.removeAttribute('class');
            }
        } else {
            listGroup.before(table);
            listGroup.remove();
        }
    }
}
/**
 * Convert all styles containing rgb colors to hexadecimal colors.
 * Note: ignores rgba colors, which are not supported in Microsoft Outlook.
 *
 * @param {JQuery} $editable
 */
function normalizeColors($editable) {
    const editable = $editable.get(0);
    for (const node of editable.querySelectorAll('[style*="rgb"]')) {
        const rgbMatch = node.getAttribute('style').match(/rgb?\(([\d\.]*,?\s?){3,4}\)/g);
        for (const rgb of rgbMatch || []) {
            node.setAttribute('style', node.getAttribute('style').replace(rgb, rgbToHex(rgb)));
        }
    }
}
/**
 * Convert all css values that use the rem unit to px.
 *
 * @param {JQuery} $editable
 * @param {Number} rootFontSize=16 The font size of the root element, in pixels
 */
function normalizeRem($editable, rootFontSize=16) {
    const editable = $editable.get(0);
    for (const node of editable.querySelectorAll('[style*="rem"]')) {
        const remMatch = node.getAttribute('style').match(/[\d\.]+\s*rem/g);
        for (const rem of remMatch || []) {
            const remValue = parseFloat(rem.replace(/[^\d\.]/g, ''));
            const pxValue = Math.round(remValue * rootFontSize * 100) / 100;
            node.setAttribute('style', node.getAttribute('style').replace(rem, pxValue + 'px'));
        }
    }
}

//--------------------------------------------------------------------------
// Private
//--------------------------------------------------------------------------

/**
 * Take an element and apply a colspan to it. In this context, this implies to
 * also apply a width to it, that corresponds to the colspan.
 *
 * @param {Element} element
 * @param {number} colspan
 */
function _applyColspan(element, colspan) {
    element.setAttribute('colspan', colspan);
    // Round to 2 decimal places.
    const width = (Math.round(+element.getAttribute('colspan') * 10000 / 12) / 100) + '%';
    element.setAttribute('width', width);
    element.style.setProperty('width', width);
}
/**
 * Take a selector and return its specificity according to the w3 specification.
 *
 * @see http://www.w3.org/TR/css3-selectors/#specificity
 * @param {string} selector
 * @returns number
 */
function _computeSpecificity(selector) {
    let a = 0;
    selector = selector.replace(/#[a-z0-9_-]+/gi, () => { a++; return ''; });
    let b = 0;
    selector = selector.replace(/(\.[a-z0-9_-]+)|(\[.*?\])/gi, () => { b++; return ''; });
    let c = 0;
    selector = selector.replace(/(^|\s+|:+)[a-z0-9_-]+/gi, a => { if (!a.includes(':not(')) c++; return ''; });
    return (a * 100) + (b * 10) + c;
}
/**
 * Take all the rules and modify them to contain information on their
 * specificity and to have normalized style.
 *
 * @see _computeSpecificity
 * @see _normalizeStyle
 * @param {Object} cssRules
 */
function _computeStyleAndSpecificityOnRules(cssRules) {
    for (const cssRule of cssRules) {
        if (!cssRule.style && cssRule.rawRule.style) {
            const style = _normalizeStyle(cssRule.rawRule.style);
            if (Object.keys(style).length) {
                Object.assign(cssRule,  { style, specificity: _computeSpecificity(cssRule.selector) });
            }
        }
    }
}
/**
 * Return an array of twelve table cells as JQuery elements.
 *
 * @returns {Element[]}
 */
function _createColumnGrid() {
    return new Array(12).fill().map(() => document.createElement('td'));
}
/**
 * Return a table element, with its default styles and attributes, as well as
 * the applicable given attributes, if any.
 *
 * @see TABLE_ATTRIBUTES
 * @see TABLE_STYLES
 * @param {NamedNodeMap | Attr[]} [attributes] default: []
 * @returns {Element}
 */
function _createTable(attributes = []) {
    const table = document.createElement('table');
    Object.entries(TABLE_ATTRIBUTES).forEach(([att, value]) => table.setAttribute(att, value));
    table.style.setProperty('width', '100%', 'important');
    for (const attr of attributes) {
        if (!(attr.name === 'width' && attr.value === '100%')) {
            table.setAttribute(attr.name, attr.value);
        }
    }
    if (table.classList.contains('o_layout')) {
        // The top mailing element inherits the body's font size and line-height
        // and should keep them.
        const layoutStyles = {...TABLE_STYLES};
        delete layoutStyles['font-size'];
        delete layoutStyles['line-height'];
        Object.entries(layoutStyles).forEach(([att, value]) => table.style[att] = value)
    } else {
        for (const styleName in TABLE_STYLES) {
            if (!('style' in attributes && attributes.style.value.includes(styleName + ':'))) {
                table.style[styleName] = TABLE_STYLES[styleName];
            }
        }
    }
    return table;
}
/**
 * Take a Bootstrap grid column element and return its size, computed by using
 * its Bootstrap classes.
 *
 * @see RE_COL_MATCH
 * @param {Element} column
 * @returns {number}
 */
function _getColumnSize(column) {
    const colMatch = column.className.match(RE_COL_MATCH);
    const colOptions = colMatch[2] && colMatch[2].substr(1).split('-');
    const colSize = colOptions && (colOptions.length === 2 ? +colOptions[1] : +colOptions[0]) || 0;
    return colSize;
}
/**
 * Take a Bootstrap grid column element and return its offset size, computed by
 * using its Bootstrap classes.
 *
 * @see RE_OFFSET_MATCH
 * @param {Element} column
 * @returns {number}
 */
function _getColumnOffsetSize(column) {
    const offsetMatch = column.className.match(RE_OFFSET_MATCH);
    const offsetOptions = offsetMatch && offsetMatch[2] && offsetMatch[2].substr(1).split('-');
    const offsetSize = offsetOptions && (offsetOptions.length === 2 ? +offsetOptions[1] : +offsetOptions[0]) || 0;
    return offsetSize;
}
/**
 * Return the CSS rules which applies on an element, tweaked so that they are
 * browser/mail client ok.
 *
 * @param {Node} node
 * @param {Object[]} Array<{selector: string;
 *                          style: {[styleName]: string};
 *                          specificity: number;}>
 * @returns {Object} {[styleName]: string}
 */
function _getMatchedCSSRules(node, cssRules) {
    node.matches = node.matches || node.webkitMatchesSelector || node.mozMatchesSelector || node.msMatchesSelector || node.oMatchesSelector;
    const styles = cssRules.map((rule) => rule.style).filter(Boolean);

    // Add inline styles at the highest specificity.
    if (node.style.length) {
        const inlineStyles = {};
        for (const styleName of node.style) {
            inlineStyles[styleName] = node.style[styleName];
        }
        styles.push(inlineStyles);
    }

    const processedStyle = {};
    for (const style of styles) {
        for (const [key, value] of Object.entries(style)) {
            if (!processedStyle[key] || !processedStyle[key].includes('important') || value.includes('important')) {
                processedStyle[key] = value;
            }
        }
    }

    for (const [key, value] of Object.entries(processedStyle)) {
        if (value && value.endsWith('important')) {
            processedStyle[key] = value.replace(/\s*!important\s*$/, '');
        }
    };

    if (processedStyle.display === 'block' && !(node.classList && ['btn-block', 'oe-nested'].some(klass => node.classList.contains(klass)))) {
        delete processedStyle.display;
    }
    if (!processedStyle['box-sizing']) {
        processedStyle['box-sizing'] = 'border-box'; // This is by default with Bootstrap.
    }

    // The css generates all the attributes separately and not in simplified
    // form. In order to have a better compatibility (outlook for example) we
    // simplify the css tags. e.g. border-left-style: none; border-bottom-s ....
    // will be simplified in border-style = none
    for (const info of [
        {name: 'margin'},
        {name: 'padding'},
        {name: 'border', suffix: '-style', defaultValue: 'none'},
    ]) {
        const positions = ['top', 'right', 'bottom', 'left'];
        const positionalKeys = positions.map(position => `${info.name}-${position}${info.suffix || ''}`);
        const hasStyles = positionalKeys.some(key => processedStyle[key]);
        const inherits = positionalKeys.some(key => ['inherit', 'initial'].includes((processedStyle[key] || '').trim()));
        if (hasStyles && !inherits) {
            const propertyName = `${info.name}${info.suffix || ''}`;
            processedStyle[propertyName] = positionalKeys.every(key => processedStyle[positionalKeys[0]] === processedStyle[key])
                ? processedStyle[propertyName] = processedStyle[positionalKeys[0]] // top = right = bottom = left => property: [top];
                : positionalKeys.map(key => processedStyle[key] || (info.defaultValue || 0)).join(' '); // property: [top] [right] [bottom] [left];
            for (const prop of positionalKeys) {
                delete processedStyle[prop];
            }
        }
    };

    if (processedStyle['border-bottom-left-radius']) {
        processedStyle['border-radius'] = processedStyle['border-bottom-left-radius'];
        delete processedStyle['border-bottom-left-radius'];
        delete processedStyle['border-bottom-right-radius'];
        delete processedStyle['border-top-left-radius'];
        delete processedStyle['border-top-right-radius'];
    }

    // If the border styling is initial we remove it to simplify the css tags
    // for compatibility. Also, since we do not send a css style tag, the
    // initial value of the border is useless.
    for (const styleName in processedStyle) {
        if (styleName.includes('border') && processedStyle[styleName] === 'initial') {
            delete processedStyle[styleName];
        }
    };

    // text-decoration rule is decomposed in -line, -color and -style. This is
    // however not supported by many browser/mail clients and the editor does
    // not allow to change -color and -style rule anyway
    if (processedStyle['text-decoration-line']) {
        processedStyle['text-decoration'] = processedStyle['text-decoration-line'];
        delete processedStyle['text-decoration-line'];
        delete processedStyle['text-decoration-color'];
        delete processedStyle['text-decoration-style'];
        delete processedStyle['text-decoration-thickness'];
    }

    // flexboxes are not supported in Windows Outlook
    for (const styleName in processedStyle) {
        if (styleName.includes('flex') || `${processedStyle[styleName]}`.includes('flex')) {
            delete processedStyle[styleName];
        }
    }

    return processedStyle;
}
let lastComputedStyleElement;
let lastComputedStyle
/**
 * Return the value of the given style property on the given element. This
 * caches the last computed style so if it's called several times in a row for
 * the same element, we don't recompute it every time.
 *
 * @param {Element} element
 * @param {string} propertyName
 * @returns
 */
function _getStylePropertyValue(element, propertyName) {
    const computedStyle = lastComputedStyleElement === element ? lastComputedStyle : getComputedStyle(element)
    lastComputedStyleElement = element;
    lastComputedStyle = computedStyle;
    return computedStyle[propertyName] || element.style.getPropertyValue(propertyName);
}
/**
 * Equivalent to JQuery's `width` method. Returns the element's visible width.
 *
 * @param {Element} element
 * @returns {Number}
 */
function _getWidth(element) {
    return parseFloat(getComputedStyle(element).width.replace('px', ''));
}
/**
 * Equivalent to JQuery's `height` method. Returns the element's visible height.
 *
 * @param {Element} element
 * @returns {Number}
 */
function _getHeight(element) {
    return parseFloat(getComputedStyle(element).height.replace('px', ''));
}
/**
 * Return true if the given element is hidden.
 *
 * @see https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/offsetParent
 * @param {Element} element
 * @returns {boolean}
 */
function _isHidden(element) {
    return element.offsetParent === null;
}
/**
 * Take a css style declaration return a "normalized" version of it (as a
 * standard object) for the purposes of emails. This means removing its styles
 * that are invalid, describe animations or aren't standard css (webkit
 * extensions). It also involves adding the "!important" suffix to styles that
 * have that priority, so they can be handled without access to the full
 * declaration.
 *
 * @param {CSSStyleDeclaration} style
 * @returns {Object} {[styleName]: string}
 */
function _normalizeStyle(style) {
    const normalizedStyle = {};
    for (const styleName of style) {
        const value = style[styleName];
        if (value && !styleName.includes('animation') && !styleName.includes('-webkit') && _.isString(value)) {
            const normalizedStyleName = styleName.replace(/-(.)/g, (a, b) => b.toUpperCase());
            normalizedStyle[styleName] = style[normalizedStyleName];
            if (style.getPropertyPriority(styleName) === 'important') {
                normalizedStyle[styleName] += ' !important';
            }
        }
    }
    return normalizedStyle;
}
/**
 * Wrap a given element into a new parent, in place.
 *
 * @param {Element} element
 * @param {string} wrapperTag
 * @param {string} [wrapperClass] optional class to apply to the wrapper
 * @param {string} [wrapperStyle] optional style to apply to the wrapper
 * @returns {Element} the wrapper
 */
 function _wrap(element, wrapperTag, wrapperClass, wrapperStyle) {
    const wrapper = document.createElement(wrapperTag);
    if (wrapperClass) {
        wrapper.className = wrapperClass;
    }
    if (wrapperStyle) {
        wrapper.style.cssText = wrapperStyle;
    }
    element.parentElement.insertBefore(wrapper, element);
    wrapper.append(element);
    return wrapper;
}

//--------------------------------------------------------------------------
// Widget
//--------------------------------------------------------------------------


FieldHtml.include({
    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------

    /**
     * @override
     */
    commitChanges: function () {
        if (this.nodeOptions['style-inline'] && this.mode === "edit") {
            this._toInline();
        }
        return this._super();
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Converts CSS dependencies to CSS-independent HTML.
     * - CSS display for attachment link -> real image
     * - Font icons -> images
     * - CSS styles -> inline styles
     *
     * @private
     */
    _toInline: function () {
        var $editable = this.wysiwyg.getEditable();
        var html = this.wysiwyg.getValue();
        const $odooEditor = $editable.closest('.odoo-editor');
        // Remove temporarily the class so that css editing will not be converted.
        $odooEditor.removeClass('odoo-editor');
        $editable.html(html);

        toInline($editable, this.cssRules, this.wysiwyg.$iframe);
        $odooEditor.addClass('odoo-editor');

        this.wysiwyg.setValue($editable.html(), {
            notifyChange: false,
        });
    },
});

export default {
    addTables: addTables,
    attachmentThumbnailToLinkImg: attachmentThumbnailToLinkImg,
    bootstrapToTable: bootstrapToTable,
    cardToTable: cardToTable,
    classToStyle: classToStyle,
    fontToImg: fontToImg,
    formatTables: formatTables,
    getCSSRules: getCSSRules,
    listGroupToTable: listGroupToTable,
    normalizeColors: normalizeColors,
    normalizeRem: normalizeRem,
    toInline: toInline,
};
