# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pytz
from datetime import datetime
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import is_html_empty, email_normalize
from odoo.addons.microsoft_calendar.utils.event_id_storage import combine_ids

ATTENDEE_CONVERTER_O2M = {
    'needsAction': 'notresponded',
    'tentative': 'tentativelyaccepted',
    'declined': 'declined',
    'accepted': 'accepted'
}
ATTENDEE_CONVERTER_M2O = {
    'none': 'needsAction',
    'notResponded': 'needsAction',
    'tentativelyAccepted': 'tentative',
    'declined': 'declined',
    'accepted': 'accepted',
    'organizer': 'accepted',
}
MAX_RECURRENT_EVENT = 720

_logger = logging.getLogger(__name__)

class Meeting(models.Model):
    _name = 'calendar.event'
    _inherit = ['calendar.event', 'microsoft.calendar.sync']

    # contains organizer event id and universal event id separated by a ':'
    microsoft_id = fields.Char('Microsoft Calendar Event Id')
    microsoft_recurrence_master_id = fields.Char('Microsoft Recurrence Master Id')

    def _get_organizer(self):
        return self.user_id

    @api.model
    def _get_microsoft_synced_fields(self):
        return {'name', 'description', 'allday', 'start', 'date_end', 'stop',
                'user_id', 'privacy',
                'attendee_ids', 'alarm_ids', 'location', 'show_as', 'active'}

    @api.model
    def _restart_microsoft_sync(self):
        self.env['calendar.event'].search(self._get_microsoft_sync_domain()).write({
            'need_sync_m': True,
        })

    @api.model_create_multi
    def create(self, vals_list):
        notify_context = self.env.context.get('dont_notify', False)

        # for a recurrent event, we do not create events separately but we directly
        # create the recurrency from the corresponding calendar.recurrence.
        # That's why, events from a recurrency have their `need_sync_m` attribute set to False.
        return super(Meeting, self.with_context(dont_notify=notify_context)).create([
            dict(vals, need_sync_m=False) if vals.get('recurrence_id') or vals.get('recurrency') else vals
            for vals in vals_list
        ])

    def _check_recurrence_overlapping(self, new_start):
        """
        Outlook does not allow to modify time fields of an event if this event crosses
        or overlaps the recurrence. In this case a 400 error with the Outlook code "ErrorOccurrenceCrossingBoundary"
        is returned. That means that the update violates the following Outlook restriction on recurrence exceptions:
        an occurrence cannot be moved to or before the day of the previous occurrence, and cannot be moved to or after
        the day of the following occurrence.
        For example: E1 E2 E3 E4 cannot becomes E1 E3 E2 E4
        """
        before_count = len(self.recurrence_id.calendar_event_ids.filtered(
            lambda e: e.start.date() < self.start.date() and e != self
        ))
        after_count = len(self.recurrence_id.calendar_event_ids.filtered(
            lambda e: e.start.date() < parse(new_start).date() and e != self
        ))
        if before_count != after_count:
            raise UserError(_(
                "Outlook limitation: in a recurrence, an event cannot be moved to or before the day of the "
                "previous event, and cannot be moved to or after the day of the following event."
            ))

    def _is_matching_timeslot(self, start, stop, allday):
        """
        Check if an event matches with the provided timeslot
        """
        self.ensure_one()

        event_start, event_stop = self._range()
        if allday:
            event_start = datetime(event_start.year, event_start.month, event_start.day, 0, 0)
            event_stop = datetime(event_stop.year, event_stop.month, event_stop.day, 0, 0)

        return (event_start, event_stop) == (start, stop)

    def write(self, values):
        recurrence_update_setting = values.get('recurrence_update')

        # check a Outlook limitation in overlapping the actual recurrence
        if recurrence_update_setting == 'self_only' and 'start' in values:
            self._check_recurrence_overlapping(values['start'])

        # if a single event becomes the base event of a recurrency, it should be first
        # removed from the Outlook calendar.
        if 'recurrency' in values and values['recurrency']:
            for e in self.filtered(lambda e: not e.recurrency and not e.recurrence_id):
                e._microsoft_delete(e._get_organizer(), e.ms_organizer_event_id, timeout=3)
                e.microsoft_id = False

        notify_context = self.env.context.get('dont_notify', False)
        res = super(Meeting, self.with_context(dont_notify=notify_context)).write(values)

        if recurrence_update_setting in ('all_events',) and len(self) == 1 \
           and values.keys() & self._get_microsoft_synced_fields():
            self.recurrence_id.need_sync_m = True
        return res

    def _get_microsoft_sync_domain(self):
        # in case of full sync, limit to a range of 1y in past and 1y in the future by default
        ICP = self.env['ir.config_parameter'].sudo()
        day_range = int(ICP.get_param('microsoft_calendar.sync.range_days', default=365))
        lower_bound = fields.Datetime.subtract(fields.Datetime.now(), days=day_range)
        upper_bound = fields.Datetime.add(fields.Datetime.now(), days=day_range)
        domain = [
            ('partner_ids.user_ids', 'in', self.env.user.id),
            ('stop', '>', lower_bound),
            ('start', '<', upper_bound),
            # Do not sync events that follow the recurrence, they are already synced at recurrence creation
            '!', '&', '&', ('recurrency', '=', True), ('recurrence_id', '!=', False), ('follow_recurrence', '=', True)
        ]
        return self._extend_microsoft_domain(domain)


    @api.model
    def _microsoft_to_odoo_values(self, microsoft_event, default_reminders=(), default_values=None, with_ids=False):
        if microsoft_event.is_cancelled():
            return {'active': False}

        sensitivity_o2m = {
            'normal': 'public',
            'private': 'private',
            'confidential': 'confidential',
        }

        commands_attendee, commands_partner = self._odoo_attendee_commands_m(microsoft_event)
        timeZone_start = pytz.timezone(microsoft_event.start.get('timeZone'))
        timeZone_stop = pytz.timezone(microsoft_event.end.get('timeZone'))
        start = parse(microsoft_event.start.get('dateTime')).astimezone(timeZone_start).replace(tzinfo=None)
        if microsoft_event.isAllDay:
            stop = parse(microsoft_event.end.get('dateTime')).astimezone(timeZone_stop).replace(tzinfo=None) - relativedelta(days=1)
        else:
            stop = parse(microsoft_event.end.get('dateTime')).astimezone(timeZone_stop).replace(tzinfo=None)
        values = default_values or {}
        values.update({
            'name': microsoft_event.subject or _("(No title)"),
            'description': microsoft_event.body and microsoft_event.body['content'],
            'location': microsoft_event.location and microsoft_event.location.get('displayName') or False,
            'user_id': microsoft_event.owner_id(self.env),
            'privacy': sensitivity_o2m.get(microsoft_event.sensitivity, self.default_get(['privacy'])['privacy']),
            'attendee_ids': commands_attendee,
            'allday': microsoft_event.isAllDay,
            'start': start,
            'stop': stop,
            'show_as': 'free' if microsoft_event.showAs == 'free' else 'busy',
            'recurrency': microsoft_event.is_recurrent()
        })
        if commands_partner:
            # Add partner_commands only if set from Microsoft. The write method on calendar_events will
            # override attendee commands if the partner_ids command is set but empty.
            values['partner_ids'] = commands_partner

        if microsoft_event.is_recurrent() and not microsoft_event.is_recurrence():
            # Propagate the follow_recurrence according to the Outlook result
            values['follow_recurrence'] = not microsoft_event.is_recurrence_outlier()

        if with_ids:
            values['microsoft_id'] = combine_ids(microsoft_event.id, microsoft_event.iCalUId)

        if microsoft_event.is_recurrent():
            values['microsoft_recurrence_master_id'] = microsoft_event.seriesMasterId

        alarm_commands = self._odoo_reminders_commands_m(microsoft_event)
        if alarm_commands:
            values['alarm_ids'] = alarm_commands

        return values

    @api.model
    def _microsoft_to_odoo_recurrence_values(self, microsoft_event, default_values=None):
        timeZone_start = pytz.timezone(microsoft_event.start.get('timeZone'))
        timeZone_stop = pytz.timezone(microsoft_event.end.get('timeZone'))
        start = parse(microsoft_event.start.get('dateTime')).astimezone(timeZone_start).replace(tzinfo=None)
        if microsoft_event.isAllDay:
            stop = parse(microsoft_event.end.get('dateTime')).astimezone(timeZone_stop).replace(tzinfo=None) - relativedelta(days=1)
        else:
            stop = parse(microsoft_event.end.get('dateTime')).astimezone(timeZone_stop).replace(tzinfo=None)
        values = default_values or {}
        values.update({
            'microsoft_id': combine_ids(microsoft_event.id, microsoft_event.iCalUId),
            'microsoft_recurrence_master_id': microsoft_event.seriesMasterId,
            'start': start,
            'stop': stop,
        })
        return values

    @api.model
    def _odoo_attendee_commands_m(self, microsoft_event):
        commands_attendee = []
        commands_partner = []

        microsoft_attendees = microsoft_event.attendees or []
        emails = [
            a.get('emailAddress').get('address')
            for a in microsoft_attendees
            if email_normalize(a.get('emailAddress').get('address'))
        ]
        existing_attendees = self.env['calendar.attendee']
        if microsoft_event.match_with_odoo_events(self.env):
            existing_attendees = self.env['calendar.attendee'].search([
                ('event_id', '=', microsoft_event.odoo_id(self.env)),
                ('email', 'in', emails)])
        elif self.env.user.partner_id.email not in emails:
            commands_attendee += [(0, 0, {'state': 'accepted', 'partner_id': self.env.user.partner_id.id})]
            commands_partner += [(4, self.env.user.partner_id.id)]
        partners = self.env['mail.thread']._mail_find_partner_from_emails(emails, records=self, force_create=True)
        attendees_by_emails = {a.email: a for a in existing_attendees}
        for email, partner, attendee_info in zip(emails, partners, microsoft_attendees):
            state = ATTENDEE_CONVERTER_M2O.get(attendee_info.get('status').get('response'), 'needsAction')

            if email in attendees_by_emails:
                # Update existing attendees
                commands_attendee += [(1, attendees_by_emails[email].id, {'state': state})]
            elif partner:
                # Create new attendees
                commands_attendee += [(0, 0, {'state': state, 'partner_id': partner.id})]
                commands_partner += [(4, partner.id)]
                if attendee_info.get('emailAddress').get('name') and not partner.name:
                    partner.name = attendee_info.get('emailAddress').get('name')
        for odoo_attendee in attendees_by_emails.values():
            # Remove old attendees
            if odoo_attendee.email not in emails:
                commands_attendee += [(2, odoo_attendee.id)]
                commands_partner += [(3, odoo_attendee.partner_id.id)]
        return commands_attendee, commands_partner

    @api.model
    def _odoo_reminders_commands_m(self, microsoft_event):
        reminders_commands = []
        if microsoft_event.isReminderOn:
            event_id = self.browse(microsoft_event.odoo_id(self.env))
            alarm_type_label = _("Notification")

            minutes = microsoft_event.reminderMinutesBeforeStart or 0
            alarm = self.env['calendar.alarm'].search([
                ('alarm_type', '=', 'notification'),
                ('duration_minutes', '=', minutes)
            ], limit=1)
            if alarm and alarm not in event_id.alarm_ids:
                reminders_commands = [(4, alarm.id)]
            elif not alarm:
                if minutes == 0:
                    interval = 'minutes'
                    duration = minutes
                    name = _("%s - At time of event", alarm_type_label)
                elif minutes % (60*24) == 0:
                    interval = 'days'
                    duration = minutes / 60 / 24
                    name = _(
                        "%(reminder_type)s - %(duration)s Days",
                        reminder_type=alarm_type_label,
                        duration=duration,
                    )
                elif minutes % 60 == 0:
                    interval = 'hours'
                    duration = minutes / 60
                    name = _(
                        "%(reminder_type)s - %(duration)s Hours",
                        reminder_type=alarm_type_label,
                        duration=duration,
                    )
                else:
                    interval = 'minutes'
                    duration = minutes
                    name = _(
                        "%(reminder_type)s - %(duration)s Minutes",
                        reminder_type=alarm_type_label,
                        duration=duration,
                    )
                reminders_commands = [(0, 0, {'duration': duration, 'interval': interval, 'name': name, 'alarm_type': 'notification'})]

            alarm_to_rm = event_id.alarm_ids.filtered(lambda a: a.alarm_type == 'notification' and a.id != alarm.id)
            if alarm_to_rm:
                reminders_commands += [(3, a.id) for a in alarm_to_rm]

        else:
            event_id = self.browse(microsoft_event.odoo_id(self.env))
            alarm_to_rm = event_id.alarm_ids.filtered(lambda a: a.alarm_type == 'notification')
            if alarm_to_rm:
                reminders_commands = [(3, a.id) for a in alarm_to_rm]
        return reminders_commands

    def _get_attendee_status_o2m(self, attendee):
        if self.user_id and self.user_id == attendee.partner_id.user_id:
            return 'organizer'
        return ATTENDEE_CONVERTER_O2M.get(attendee.state, 'None')

    def _microsoft_values(self, fields_to_sync, initial_values={}):
        values = dict(initial_values)
        if not fields_to_sync:
            return values

        microsoft_guid = self.env['ir.config_parameter'].sudo().get_param('microsoft_calendar.microsoft_guid', False)

        if self.microsoft_recurrence_master_id and 'type' not in values:
            values['seriesMasterId'] = self.microsoft_recurrence_master_id
            values['type'] = 'exception'

        if 'name' in fields_to_sync:
            values['subject'] = self.name or ''

        if 'description' in fields_to_sync:
            values['body'] = {
                'content': self.description if not is_html_empty(self.description) else '',
                'contentType': "html",
            }

        if any(x in fields_to_sync for x in ['allday', 'start', 'date_end', 'stop']):
            if self.allday:
                start = {'dateTime': self.start_date.isoformat(), 'timeZone': 'Europe/London'}
                end = {'dateTime': (self.stop_date + relativedelta(days=1)).isoformat(), 'timeZone': 'Europe/London'}
            else:
                start = {'dateTime': pytz.utc.localize(self.start).isoformat(), 'timeZone': 'Europe/London'}
                end = {'dateTime': pytz.utc.localize(self.stop).isoformat(), 'timeZone': 'Europe/London'}

            values['start'] = start
            values['end'] = end
            values['isAllDay'] = self.allday

        if 'location' in fields_to_sync:
            values['location'] = {'displayName': self.location or ''}

        if 'alarm_ids' in fields_to_sync:
            alarm_id = self.alarm_ids.filtered(lambda a: a.alarm_type == 'notification')[:1]
            values['isReminderOn'] = bool(alarm_id)
            values['reminderMinutesBeforeStart'] = alarm_id.duration_minutes

        if 'user_id' in fields_to_sync:
            values['organizer'] = {'emailAddress': {'address': self.user_id.email or '', 'name': self.user_id.display_name or ''}}
            values['isOrganizer'] = self.user_id == self.env.user

        if 'attendee_ids' in fields_to_sync:
            attendees = self.attendee_ids.filtered(lambda att: att.partner_id not in self.user_id.partner_id)
            values['attendees'] = [
                {
                    'emailAddress': {'address': attendee.email or '', 'name': attendee.display_name or ''},
                    'status': {'response': self._get_attendee_status_o2m(attendee)}
                } for attendee in attendees]

        if 'privacy' in fields_to_sync or 'show_as' in fields_to_sync:
            values['showAs'] = self.show_as
            sensitivity_o2m = {
                'public': 'normal',
                'private': 'private',
                'confidential': 'confidential',
            }
            values['sensitivity'] = sensitivity_o2m.get(self.privacy)

        if 'active' in fields_to_sync and not self.active:
            values['isCancelled'] = True

        if values.get('type') == 'seriesMaster':
            recurrence = self.recurrence_id
            pattern = {
                'interval': recurrence.interval
            }
            if recurrence.rrule_type in ['daily', 'weekly']:
                pattern['type'] = recurrence.rrule_type
            else:
                prefix = 'absolute' if recurrence.month_by == 'date' else 'relative'
                pattern['type'] = recurrence.rrule_type and prefix + recurrence.rrule_type.capitalize()

            if recurrence.month_by == 'date':
                pattern['dayOfMonth'] = recurrence.day

            if recurrence.month_by == 'day' or recurrence.rrule_type == 'weekly':
                pattern['daysOfWeek'] = [
                    weekday_name for weekday_name, weekday in {
                        'monday': recurrence.mon,
                        'tuesday': recurrence.tue,
                        'wednesday': recurrence.wed,
                        'thursday': recurrence.thu,
                        'friday': recurrence.fri,
                        'saturday': recurrence.sat,
                        'sunday': recurrence.sun,
                    }.items() if weekday]
                pattern['firstDayOfWeek'] = 'sunday'

            if recurrence.rrule_type == 'monthly' and recurrence.month_by == 'day':
                byday_selection = {
                    '1': 'first',
                    '2': 'second',
                    '3': 'third',
                    '4': 'fourth',
                    '-1': 'last',
                }
                pattern['index'] = byday_selection[recurrence.byday]

            dtstart = recurrence.dtstart or fields.Datetime.now()
            rule_range = {
                'startDate': (dtstart.date()).isoformat()
            }

            if recurrence.end_type == 'count':  # e.g. stop after X occurence
                rule_range['numberOfOccurrences'] = min(recurrence.count, MAX_RECURRENT_EVENT)
                rule_range['type'] = 'numbered'
            elif recurrence.end_type == 'forever':
                rule_range['numberOfOccurrences'] = MAX_RECURRENT_EVENT
                rule_range['type'] = 'numbered'
            elif recurrence.end_type == 'end_date':  # e.g. stop after 12/10/2020
                rule_range['endDate'] = recurrence.until.isoformat()
                rule_range['type'] = 'endDate'

            values['recurrence'] = {
                'pattern': pattern,
                'range': rule_range
            }

        return values

    def _ensure_attendees_have_email(self):
        invalid_event_ids = self.env['calendar.event'].search_read(
            domain=[('id', 'in', self.ids), ('attendee_ids.partner_id.email', '=', False)],
            fields=['display_time', 'display_name'],
            order='start',
        )
        if invalid_event_ids:
            list_length_limit = 50
            total_invalid_events = len(invalid_event_ids)
            invalid_event_ids = invalid_event_ids[:list_length_limit]
            invalid_events = ['\t- %s: %s' % (event['display_time'], event['display_name'])
                              for event in invalid_event_ids]
            invalid_events = '\n'.join(invalid_events)
            details = "(%d/%d)" % (list_length_limit, total_invalid_events) if list_length_limit < total_invalid_events else "(%d)" % total_invalid_events
            raise ValidationError(_("For a correct synchronization between Odoo and Outlook Calendar, "
                                    "all attendees must have an email address. However, some events do "
                                    "not respect this condition. As long as the events are incorrect, "
                                    "the calendars will not be synchronized."
                                    "\nEither update the events/attendees or archive these events %s:"
                                    "\n%s", details, invalid_events))

    def _microsoft_values_occurence(self, initial_values={}):
        values = initial_values
        values['type'] = 'occurrence'

        if self.allday:
            start = {'dateTime': self.start_date.isoformat(), 'timeZone': 'Europe/London'}
            end = {'dateTime': (self.stop_date + relativedelta(days=1)).isoformat(), 'timeZone': 'Europe/London'}
        else:
            start = {'dateTime': pytz.utc.localize(self.start).isoformat(), 'timeZone': 'Europe/London'}
            end = {'dateTime': pytz.utc.localize(self.stop).isoformat(), 'timeZone': 'Europe/London'}

        values['start'] = start
        values['end'] = end
        values['isAllDay'] = self.allday

        return values

    def _cancel_microsoft(self):
        """
        Cancel an Microsoft event.
        There are 2 cases:
          1) the organizer is an Odoo user: he's the only one able to delete the Odoo event. Attendees can just decline.
          2) the organizer is NOT an Odoo user: any attendee should remove the Odoo event.
        """
        user = self.env.user
        records = self.filtered(lambda e: not e.user_id or e.user_id == user)
        super(Meeting, records)._cancel_microsoft()
        attendees = (self - records).attendee_ids.filtered(lambda a: a.partner_id == user.partner_id)
        attendees.do_decline()
