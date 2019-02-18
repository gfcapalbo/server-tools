# -*- coding: utf-8 -*-
# © 2016-2018 Therp BV <http://therp.nl>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import json
import pytz
from dateutil.rrule import rrule, rruleset
from dateutil.tz import gettz
from odoo import fields, models
_RRULE_DATETIME_FIELDS = ['_until', '_dtstart']
_RRULE_SCALAR_FIELDS = [
    '_wkst', '_cache', '_until', '_dtstart', '_count', '_freq', '_interval',
]
_RRULE_ZERO_IS_NOT_NONE = ['_freq']


class LocalRRuleSet(rruleset):
    """An rruleset that yields the naive utc representation of a date if the
    original date was timezone aware"""
    def __iter__(self):
        for date in rruleset.__iter__(self):
            if not date.tzinfo:
                yield date
            else:
                yield date.astimezone(pytz.utc).replace(tzinfo=None)


class SerializableRRuleSet(list):
    """Getting our rule set json stringified is tricky, because we can't
    just inject our own json encoder. Now we pretend our set is a list,
    then json.dumps will try to iterate, which is why we can do our specific
    stuff in __iter__"""
    def __init__(self, *args):
        self._rrule = list(args)
        self._exdate = []
        self._rdate = []
        self.tz = None
        super(SerializableRRuleSet, self).__init__(self)

    def __iter__(self):
        for rule in self._rrule:
            yield dict(type='rrule', **{
                key[1:]:
                fields.Datetime.to_string(
                    getattr(rule, key) if
                    not self.tz or not getattr(rule, key) or
                    not getattr(rule, key).tzinfo
                    else getattr(rule, key).astimezone(pytz.utc)
                )
                if key in _RRULE_DATETIME_FIELDS
                else
                [] if getattr(rule, key) is None and
                key not in _RRULE_SCALAR_FIELDS
                else
                list(getattr(rule, key)) if key not in _RRULE_SCALAR_FIELDS
                else getattr(rule, key)
                for key in [
                    '_byhour', '_wkst', '_bysecond', '_bymonthday',
                    '_byweekno', '_bysetpos', '_cache', '_bymonth',
                    '_byyearday', '_byweekday', '_byminute',
                    '_until', '_dtstart', '_count', '_freq', '_interval',
                    '_byeaster',
                ]
            })
        for exdate in self._exdate:
            yield dict(type='exdate', date=fields.Datetime.to_string(exdate))
        for rdate in self._rdate:
            yield dict(type='rdate', date=fields.Datetime.to_string(rdate))
        if self.tz:
            yield dict(type='tz', tz=self.tz)
        # TODO: implement exrule

    def __call__(self, default_self=None):
        """convert self to a proper rruleset for iteration.
        If we use defaults on our field, this will be called too with
        and empty recordset as parameter. In this case, we need self"""
        if isinstance(default_self, models.BaseModel):
            return self
        result = LocalRRuleSet()
        result._rrule = self._rrule
        result._exdate = self._exdate
        result._rdate = self._rdate
        return result

    def __nonzero__(self):
        return bool(self._rrule) or bool(self._rdate)

    def __repr__(self):
        return ', '.join(str(a) for a in self)

    def __getitem__(self, key):
        return rruleset.__getitem__(self(), key)

    def __getslice__(self, i, j):
        return rruleset.__getitem__(self(), slice(i, j))

    def __ne__(self, o):
        return not self.__eq__(o)

    def __eq__(self, o):
        return self.__repr__() == o.__repr__()

    def between(self, after, before, inc=False):
        return self().between(after, before, inc=inc)

    def after(self, dt, inc=False):
        return self().after(dt, inc=inc)

    def before(self, dt, inc=False):
        return self().before(dt, inc=inc)

    def count(self):
        return self().count()


class FieldRRule(fields.Field):
    type = 'rrule'
    column_type = ('text', 'text')
    _slots = {
        'stable_times': None,
    }

    def convert_to_cache(self, value, record, validate=True):
        result = SerializableRRuleSet()
        if isinstance(value, basestring):
            value = json.loads(value)
        if not value:
            return result
        if isinstance(value, SerializableRRuleSet):
            if self.stable_times and not value.tz:
                self._add_tz(value, record.env.user.tz or 'utc')
            return value
        assert isinstance(value, list), 'An RRULE\'s content must be a list'
        tz = None
        for data in value:
            assert isinstance(data, dict), 'The list must contain dictionaries'
            assert 'type' in data, 'The dictionary must contain a type'
            data_type = data['type']
            if hasattr(self, 'convert_to_cache_parse_data_%s' % data_type):
                data = getattr(
                    self, 'convert_to_cache_parse_data_%s' % data_type
                )(record, data)
            if data_type == 'rrule':
                result._rrule.append(rrule(**data))
            elif data_type == 'exdate':
                result._exdate.append(
                    fields.Datetime.from_string(data['date'])
                )
            elif data_type == 'rdate':
                result._rdate.append(fields.Datetime.from_string(data['date']))
            elif data_type == 'tz' and self.stable_times:
                tz = data['tz']
            else:
                raise ValueError('Unknown type given')
        if self.stable_times:
            self._add_tz(result, tz or record.env.user.tz or 'utc')
        return result

    def convert_to_cache_parse_data_rrule(self, record, data):
        """parse a data dictionary from the database"""
        return {
            key: fields.Datetime.from_string(value)
            if '_%s' % key in _RRULE_DATETIME_FIELDS
            else map(int, value)
            if value and '_%s' % key not in _RRULE_SCALAR_FIELDS
            else int(value) if value
            else None
            if not value and '_%s' % key not in _RRULE_ZERO_IS_NOT_NONE
            else value
            for key, value in data.iteritems()
            if key != 'type'
        }

    def convert_to_column(self, value, record):
        return json.dumps(value)

    def _add_tz(self, value, tz):
        """set the timezone on an rruleset and adjust dates there"""
        value.tz = tz
        tz = gettz(tz)
        if not tz:
            value.tz = None
            return
        for rule in value._rrule:
            for fieldname in _RRULE_DATETIME_FIELDS:
                date = getattr(rule, fieldname)
                if not date:
                    continue
                setattr(
                    rule, fieldname,
                    date.replace(tzinfo=pytz.utc).astimezone(tz),
                )
            rule._tzinfo = tz
            rule._timeset = tuple([
                rule._dtstart.replace(
                    hour=time.hour,
                    minute=time.minute,
                    second=time.second,
                    tzinfo=pytz.utc,
                ).astimezone(tz).timetz()
                if not time.tzinfo else time
                for time in rule._timeset
            ])
        value._exdate = [
            _date.replace(tzinfo=pytz.utc).astimezone(tz)
            for _date in value._exdate
        ]
        value._rdate = [
            _date.replace(tzinfo=pytz.utc).astimezone(tz)
            for _date in value._rdate
        ]
