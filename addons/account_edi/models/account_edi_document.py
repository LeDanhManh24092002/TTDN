# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from psycopg2 import OperationalError
import base64
import logging

_logger = logging.getLogger(__name__)

DEFAULT_BLOCKING_LEVEL = 'error'


class AccountEdiDocument(models.Model):
    _name = 'account.edi.document'
    _description = 'Electronic Document for an account.move'

    # == Stored fields ==
    move_id = fields.Many2one('account.move', required=True, ondelete='cascade')
    edi_format_id = fields.Many2one('account.edi.format', required=True)
    attachment_id = fields.Many2one('ir.attachment', help='The file generated by edi_format_id when the invoice is posted (and this document is processed).')
    state = fields.Selection([('to_send', 'To Send'), ('sent', 'Sent'), ('to_cancel', 'To Cancel'), ('cancelled', 'Cancelled')])
    error = fields.Html(help='The text of the last error that happened during Electronic Invoice operation.')
    blocking_level = fields.Selection(
        selection=[('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')],
        help="Blocks the current operation of the document depending on the error severity:\n"
        "  * Info: the document is not blocked and everything is working as it should.\n"
        "  * Warning: there is an error that doesn't prevent the current Electronic Invoicing operation to succeed.\n"
        "  * Error: there is an error that blocks the current Electronic Invoicing operation.")

    # == Not stored fields ==
    name = fields.Char(related='attachment_id.name')
    edi_format_name = fields.Char(string='Format Name', related='edi_format_id.name')
    edi_content = fields.Binary(compute='_compute_edi_content', compute_sudo=True)

    _sql_constraints = [
        (
            'unique_edi_document_by_move_by_format',
            'UNIQUE(edi_format_id, move_id)',
            'Only one edi document by move by format',
        ),
    ]

    @api.depends('move_id', 'error', 'state')
    def _compute_edi_content(self):
        for doc in self:
            res = b''
            if doc.state in ('to_send', 'to_cancel'):
                move = doc.move_id
                config_errors = doc.edi_format_id._check_move_configuration(move)
                if config_errors:
                    res = base64.b64encode('\n'.join(config_errors).encode('UTF-8'))
                elif move.is_invoice(include_receipts=True) and doc.edi_format_id._is_required_for_invoice(move):
                    res = base64.b64encode(doc.edi_format_id._get_invoice_edi_content(doc.move_id))
                elif move.payment_id and doc.edi_format_id._is_required_for_payment(move):
                    res = base64.b64encode(doc.edi_format_id._get_payment_edi_content(doc.move_id))
            doc.edi_content = res

    def action_export_xml(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url':  '/web/content/account.edi.document/%s/edi_content' % self.id
        }

    def _prepare_jobs(self):
        """Creates a list of jobs to be performed by '_process_job' for the documents in self.
        Each document represent a job, BUT if multiple documents have the same state, edi_format_id,
        doc_type (invoice or payment) and company_id AND the edi_format_id supports batching, they are grouped
        into a single job.

        :returns:         A list of tuples (documents, doc_type)
        * documents:      The documents related to this job. If edi_format_id does not support batch, length is one
        * doc_type:       Are the moves of this job invoice or payments ?
        """

        # Classify jobs by (edi_format, edi_doc.state, doc_type, move.company_id, custom_key)
        to_process = {}
        documents = self.filtered(lambda d: d.state in ('to_send', 'to_cancel') and d.blocking_level != 'error')
        for edi_doc in documents:
            move = edi_doc.move_id
            edi_format = edi_doc.edi_format_id
            if move.is_invoice(include_receipts=True):
                doc_type = 'invoice'
            elif move.payment_id or move.statement_line_id:
                doc_type = 'payment'
            else:
                continue

            custom_key = edi_format._get_batch_key(edi_doc.move_id, edi_doc.state)
            key = (edi_format, edi_doc.state, doc_type, move.company_id, custom_key)
            to_process.setdefault(key, self.env['account.edi.document'])
            to_process[key] |= edi_doc

        # Order payments/invoice and create batches.
        invoices = []
        payments = []
        for key, documents in to_process.items():
            edi_format, state, doc_type, company_id, custom_key = key
            target = invoices if doc_type == 'invoice' else payments
            batch = self.env['account.edi.document']
            for doc in documents:
                if edi_format._support_batching(move=doc.move_id, state=state, company=company_id):
                    batch |= doc
                else:
                    target.append((doc, doc_type))
            if batch:
                target.append((batch, doc_type))
        return invoices + payments

    @api.model
    def _process_job(self, documents, doc_type):
        """Post or cancel move_id (invoice or payment) by calling the related methods on edi_format_id.
        Invoices are processed before payments.

        :param documents: The documents related to this job. If edi_format_id does not support batch, length is one
        :param doc_type:  Are the moves of this job invoice or payments ?
        """
        def _postprocess_post_edi_results(documents, edi_result):
            attachments_to_unlink = self.env['ir.attachment']
            for document in documents:
                move = document.move_id
                move_result = edi_result.get(move, {})
                if move_result.get('attachment'):
                    old_attachment = document.attachment_id
                    document.attachment_id = move_result['attachment']
                    if not old_attachment.res_model or not old_attachment.res_id:
                        attachments_to_unlink |= old_attachment
                if move_result.get('success') is True:
                    document.write({
                        'state': 'sent',
                        'error': False,
                        'blocking_level': False,
                    })
                    if doc_type == 'invoice':
                        reconciled_lines = move.line_ids.filtered(lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))
                        reconciled_amls = reconciled_lines.mapped('matched_debit_ids.debit_move_id') \
                                          | reconciled_lines.mapped('matched_credit_ids.credit_move_id')
                        reconciled_amls.move_id._update_payments_edi_documents()
                else:
                    document.write({
                        'error': move_result.get('error', False),
                        'blocking_level': move_result.get('blocking_level', DEFAULT_BLOCKING_LEVEL) if 'error' in move_result else False,
                    })

            # Attachments that are not explicitly linked to a business model could be removed because they are not
            # supposed to have any traceability from the user.
            attachments_to_unlink.unlink()

        def _postprocess_cancel_edi_results(documents, edi_result):
            moves_to_cancel = self.env['account.move'] # Avoid duplicates
            attachments_to_unlink = self.env['ir.attachment']
            for document in documents:
                move = document.move_id
                move_result = edi_result.get(move, {})
                if move_result.get('success') is True:
                    old_attachment = document.sudo().attachment_id
                    document.write({
                        'state': 'cancelled',
                        'error': False,
                        'attachment_id': False,
                        'blocking_level': False,
                    })

                    if move.state == 'posted' and all(
                        doc.state == 'cancelled'
                        or not doc.edi_format_id._needs_web_services()
                        for doc in move.edi_document_ids
                    ):
                        # The user requested a cancellation of the EDI and it has been approved. Then, the invoice
                        # can be safely cancelled.
                        moves_to_cancel |= move

                    if not old_attachment.res_model or not old_attachment.res_id:
                        attachments_to_unlink |= old_attachment

                else:
                    document.write({
                        'error': move_result.get('error', False),
                        'blocking_level': move_result.get('blocking_level', DEFAULT_BLOCKING_LEVEL) if move_result.get('error') else False,
                    })
            if moves_to_cancel:
                moves_to_cancel.button_draft()
                moves_to_cancel.button_cancel()

            # Attachments that are not explicitly linked to a business model could be removed because they are not
            # supposed to have any traceability from the user.
            attachments_to_unlink.sudo().unlink()

        documents.edi_format_id.ensure_one()  # All account.edi.document of a job should have the same edi_format_id
        documents.move_id.company_id.ensure_one()  # All account.edi.document of a job should be from the same company
        if len(set(doc.state for doc in documents)) != 1:
            raise ValueError('All account.edi.document of a job should have the same state')

        edi_format = documents.edi_format_id
        state = documents[0].state
        if doc_type == 'invoice':
            if state == 'to_send':
                invoices = documents.move_id
                with invoices._send_only_when_ready():
                    edi_result = edi_format._post_invoice_edi(invoices)
                    _postprocess_post_edi_results(documents, edi_result)
            elif state == 'to_cancel':
                edi_result = edi_format._cancel_invoice_edi(documents.move_id)
                _postprocess_cancel_edi_results(documents, edi_result)

        elif doc_type == 'payment':
            if state == 'to_send':
                edi_result = edi_format._post_payment_edi(documents.move_id)
                _postprocess_post_edi_results(documents, edi_result)
            elif state == 'to_cancel':
                edi_result = edi_format._cancel_payment_edi(documents.move_id)
                _postprocess_cancel_edi_results(documents, edi_result)

    def _process_documents_no_web_services(self):
        """ Post and cancel all the documents that don't need a web service.
        """
        jobs = self.filtered(lambda d: not d.edi_format_id._needs_web_services())._prepare_jobs()
        for documents, doc_type in jobs:
            self._process_job(documents, doc_type)

    def _process_documents_web_services(self, job_count=None, with_commit=True):
        ''' Post and cancel all the documents that need a web service.

        :param job_count:   The maximum number of jobs to process if specified.
        :param with_commit: Flag indicating a commit should be made between each job.
        :return:            The number of remaining jobs to process.
        '''
        all_jobs = self.filtered(lambda d: d.edi_format_id._needs_web_services())._prepare_jobs()
        jobs_to_process = all_jobs[0:job_count] if job_count else all_jobs

        for documents, doc_type in jobs_to_process:
            move_to_lock = documents.move_id
            attachments_potential_unlink = documents.attachment_id.filtered(lambda a: not a.res_model and not a.res_id)
            try:
                with self.env.cr.savepoint(flush=False):
                    self._cr.execute('SELECT * FROM account_edi_document WHERE id IN %s FOR UPDATE NOWAIT', [tuple(documents.ids)])
                    self._cr.execute('SELECT * FROM account_move WHERE id IN %s FOR UPDATE NOWAIT', [tuple(move_to_lock.ids)])

                    # Locks the attachments that might be unlinked
                    if attachments_potential_unlink:
                        self._cr.execute('SELECT * FROM ir_attachment WHERE id IN %s FOR UPDATE NOWAIT', [tuple(attachments_potential_unlink.ids)])

            except OperationalError as e:
                if e.pgcode == '55P03':
                    _logger.debug('Another transaction already locked documents rows. Cannot process documents.')
                    if not with_commit:
                        raise UserError(_('This document is being sent by another process already. '))
                    continue
                else:
                    raise e
            self._process_job(documents, doc_type)
            if with_commit and len(jobs_to_process) > 1:
                self.env.cr.commit()

        return len(all_jobs) - len(jobs_to_process)

    @api.model
    def _cron_process_documents_web_services(self, job_count=None):
        ''' Method called by the EDI cron processing all web-services.

        :param job_count: Limit explicitely the number of web service calls. If not provided, process all.
        '''
        edi_documents = self.search([('state', 'in', ('to_send', 'to_cancel')), ('move_id.state', '=', 'posted')])
        nb_remaining_jobs = edi_documents._process_documents_web_services(job_count=job_count)

        # Mark the CRON to be triggered again asap since there is some remaining jobs to process.
        if nb_remaining_jobs > 0:
            self.env.ref('account_edi.ir_cron_edi_network')._trigger()
