# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


"""
Miscellaneous tools used by OpenERP.
"""
import cProfile
import collections
import datetime
import hmac as hmac_lib
import hashlib
import io
import itertools
import os
import pickle as pickle_
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import unicodedata
import zipfile
from collections import OrderedDict
from collections.abc import Iterable, Mapping, MutableMapping, MutableSet
from contextlib import contextmanager
from difflib import HtmlDiff
from functools import wraps
from itertools import islice, groupby as itergroupby
from operator import itemgetter

import babel
import babel.dates
import markupsafe
import passlib.utils
import pytz
import werkzeug.utils
from lxml import etree, objectify

import odoo
import odoo.addons
# get_encodings, ustr and exception_to_unicode were originally from tools.misc.
# There are moved to loglevels until we refactor tools.
from odoo.loglevels import get_encodings, ustr, exception_to_unicode     # noqa
from . import pycompat
from .cache import *
from .config import config
from .parse_version import parse_version
from .which import which

_logger = logging.getLogger(__name__)

# List of etree._Element subclasses that we choose to ignore when parsing XML.
# We include the *Base ones just in case, currently they seem to be subclasses of the _* ones.
SKIPPED_ELEMENT_TYPES = (etree._Comment, etree._ProcessingInstruction, etree.CommentBase, etree.PIBase, etree._Entity)

# Configure default global parser
etree.set_default_parser(etree.XMLParser(resolve_entities=False))
default_parser = etree.XMLParser(resolve_entities=False, remove_blank_text=True)
default_parser.set_element_class_lookup(objectify.ObjectifyElementClassLookup())
objectify.set_default_parser(default_parser)

NON_BREAKING_SPACE = u'\N{NO-BREAK SPACE}'

#----------------------------------------------------------
# Subprocesses
#----------------------------------------------------------

def find_in_path(name):
    path = os.environ.get('PATH', os.defpath).split(os.pathsep)
    if config.get('bin_path') and config['bin_path'] != 'None':
        path.append(config['bin_path'])
    return which(name, path=os.pathsep.join(path))

def _exec_pipe(prog, args, env=None):
    cmd = (prog,) + args
    # on win32, passing close_fds=True is not compatible
    # with redirecting std[in/err/out]
    close_fds = os.name=="posix"
    pop = subprocess.Popen(cmd, bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=close_fds, env=env)
    return pop.stdin, pop.stdout

def exec_command_pipe(name, *args):
    prog = find_in_path(name)
    if not prog:
        raise Exception('Command `%s` not found.' % name)
    return _exec_pipe(prog, args)

#----------------------------------------------------------
# Postgres subprocesses
#----------------------------------------------------------

def find_pg_tool(name):
    path = None
    if config['pg_path'] and config['pg_path'] != 'None':
        path = config['pg_path']
    try:
        return which(name, path=path)
    except IOError:
        raise Exception('Command `%s` not found.' % name)

def exec_pg_environ():
    """
    Force the database PostgreSQL environment variables to the database
    configuration of Odoo.

    Note: On systems where pg_restore/pg_dump require an explicit password
    (i.e.  on Windows where TCP sockets are used), it is necessary to pass the
    postgres user password in the PGPASSWORD environment variable or in a
    special .pgpass file.

    See also http://www.postgresql.org/docs/8.4/static/libpq-envars.html
    """
    env = os.environ.copy()
    if odoo.tools.config['db_host']:
        env['PGHOST'] = odoo.tools.config['db_host']
    if odoo.tools.config['db_port']:
        env['PGPORT'] = str(odoo.tools.config['db_port'])
    if odoo.tools.config['db_user']:
        env['PGUSER'] = odoo.tools.config['db_user']
    if odoo.tools.config['db_password']:
        env['PGPASSWORD'] = odoo.tools.config['db_password']
    return env

def exec_pg_command(name, *args):
    prog = find_pg_tool(name)
    env = exec_pg_environ()
    args2 = (prog,) + args
    rc = subprocess.call(args2, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if rc:
        raise Exception('Postgres subprocess %s error %s' % (args2, rc))

def exec_pg_command_pipe(name, *args):
    prog = find_pg_tool(name)
    env = exec_pg_environ()
    return _exec_pipe(prog, args, env)

#----------------------------------------------------------
# File paths
#----------------------------------------------------------

def file_path(file_path, filter_ext=('',), env=None):
    """Verify that a file exists under a known `addons_path` directory and return its full path.

    Examples::

    >>> file_path('hr')
    >>> file_path('hr/static/description/icon.png')
    >>> file_path('hr/static/description/icon.png', filter_ext=('.png', '.jpg'))

    :param str file_path: absolute file path, or relative path within any `addons_path` directory
    :param list[str] filter_ext: optional list of supported extensions (lowercase, with leading dot)
    :param env: optional environment, required for a file path within a temporary directory
        created using `file_open_temporary_directory()`
    :return: the absolute path to the file
    :raise FileNotFoundError: if the file is not found under the known `addons_path` directories
    :raise ValueError: if the file doesn't have one of the supported extensions (`filter_ext`)
    """
    root_path = os.path.abspath(config['root_path'])
    addons_paths = odoo.addons.__path__ + [root_path]
    if env and hasattr(env.transaction, '__file_open_tmp_paths'):
        addons_paths += env.transaction.__file_open_tmp_paths
    is_abs = os.path.isabs(file_path)
    normalized_path = os.path.normpath(os.path.normcase(file_path))

    if filter_ext and not normalized_path.lower().endswith(filter_ext):
        raise ValueError("Unsupported file: " + file_path)

    # ignore leading 'addons/' if present, it's the final component of root_path, but
    # may sometimes be included in relative paths
    if normalized_path.startswith('addons' + os.sep):
        normalized_path = normalized_path[7:]

    for addons_dir in addons_paths:
        # final path sep required to avoid partial match
        parent_path = os.path.normpath(os.path.normcase(addons_dir)) + os.sep
        fpath = (normalized_path if is_abs else
                 os.path.normpath(os.path.normcase(os.path.join(parent_path, normalized_path))))
        if fpath.startswith(parent_path) and os.path.exists(fpath):
            return fpath

    raise FileNotFoundError("File not found: " + file_path)

def file_open(name, mode="r", filter_ext=None, env=None):
    """Open a file from within the addons_path directories, as an absolute or relative path.

    Examples::

    >>> file_open('hr/static/description/icon.png')
    >>> file_open('hr/static/description/icon.png', filter_ext=('.png', '.jpg'))
    >>> with file_open('/opt/odoo/addons/hr/static/description/icon.png', 'rb') as f:
    ...     contents = f.read()

    :param name: absolute or relative path to a file located inside an addon
    :param mode: file open mode, as for `open()`
    :param list[str] filter_ext: optional list of supported extensions (lowercase, with leading dot)
    :param env: optional environment, required to open a file within a temporary directory
        created using `file_open_temporary_directory()`
    :return: file object, as returned by `open()`
    :raise FileNotFoundError: if the file is not found under the known `addons_path` directories
    :raise ValueError: if the file doesn't have one of the supported extensions (`filter_ext`)
    """
    path = file_path(name, filter_ext=filter_ext, env=env)
    if os.path.isfile(path):
        if 'b' not in mode:
            # Force encoding for text mode, as system locale could affect default encoding,
            # even with the latest Python 3 versions.
            # Note: This is not covered by a unit test, due to the platform dependency.
            #       For testing purposes you should be able to force a non-UTF8 encoding with:
            #         `sudo locale-gen fr_FR; LC_ALL=fr_FR.iso8859-1 python3 ...'
            # See also PEP-540, although we can't rely on that at the moment.
            return open(path, mode, encoding="utf-8")
        return open(path, mode)
    raise FileNotFoundError("Not a file: " + name)


@contextmanager
def file_open_temporary_directory(env):
    """Create and return a temporary directory added to the directories `file_open` is allowed to read from.

    `file_open` will be allowed to open files within the temporary directory
    only for environments of the same transaction than `env`.
    Meaning, other transactions/requests from other users or even other databases
    won't be allowed to open files from this directory.

    Examples::

        >>> with odoo.tools.file_open_temporary_directory(self.env) as module_dir:
        ...    with zipfile.ZipFile('foo.zip', 'r') as z:
        ...        z.extract('foo/__manifest__.py', module_dir)
        ...    with odoo.tools.file_open('foo/__manifest__.py', env=self.env) as f:
        ...        manifest = f.read()

    :param env: environment for which the temporary directory is created.
    :return: the absolute path to the created temporary directory
    """
    assert not hasattr(env.transaction, '__file_open_tmp_paths'), 'Reentrancy is not implemented for this method'
    with tempfile.TemporaryDirectory() as module_dir:
        try:
            env.transaction.__file_open_tmp_paths = (module_dir,)
            yield module_dir
        finally:
            del env.transaction.__file_open_tmp_paths


#----------------------------------------------------------
# iterables
#----------------------------------------------------------
def flatten(list):
    """Flatten a list of elements into a unique list
    Author: Christophe Simonis (christophe@tinyerp.com)

    Examples::
    >>> flatten(['a'])
    ['a']
    >>> flatten('b')
    ['b']
    >>> flatten( [] )
    []
    >>> flatten( [[], [[]]] )
    []
    >>> flatten( [[['a','b'], 'c'], 'd', ['e', [], 'f']] )
    ['a', 'b', 'c', 'd', 'e', 'f']
    >>> t = (1,2,(3,), [4, 5, [6, [7], (8, 9), ([10, 11, (12, 13)]), [14, [], (15,)], []]])
    >>> flatten(t)
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    """
    r = []
    for e in list:
        if isinstance(e, (bytes, str)) or not isinstance(e, collections.abc.Iterable):
            r.append(e)
        else:
            r.extend(flatten(e))
    return r

def reverse_enumerate(l):
    """Like enumerate but in the other direction

    Usage::
    >>> a = ['a', 'b', 'c']
    >>> it = reverse_enumerate(a)
    >>> it.next()
    (2, 'c')
    >>> it.next()
    (1, 'b')
    >>> it.next()
    (0, 'a')
    >>> it.next()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration
    """
    return zip(range(len(l)-1, -1, -1), reversed(l))

def partition(pred, elems):
    """ Return a pair equivalent to:
        ``filter(pred, elems), filter(lambda x: not pred(x), elems)` """
    yes, nos = [], []
    for elem in elems:
        (yes if pred(elem) else nos).append(elem)
    return yes, nos

def topological_sort(elems):
    """ Return a list of elements sorted so that their dependencies are listed
    before them in the result.

    :param elems: specifies the elements to sort with their dependencies; it is
        a dictionary like `{element: dependencies}` where `dependencies` is a
        collection of elements that must appear before `element`. The elements
        of `dependencies` are not required to appear in `elems`; they will
        simply not appear in the result.

    :returns: a list with the keys of `elems` sorted according to their
        specification.
    """
    # the algorithm is inspired by [Tarjan 1976],
    # http://en.wikipedia.org/wiki/Topological_sorting#Algorithms
    result = []
    visited = set()

    def visit(n):
        if n not in visited:
            visited.add(n)
            if n in elems:
                # first visit all dependencies of n, then append n to result
                for it in elems[n]:
                    visit(it)
                result.append(n)

    for el in elems:
        visit(el)

    return result


def merge_sequences(*iterables):
    """ Merge several iterables into a list. The result is the union of the
        iterables, ordered following the partial order given by the iterables,
        with a bias towards the end for the last iterable::

            seq = merge_sequences(['A', 'B', 'C'])
            assert seq == ['A', 'B', 'C']

            seq = merge_sequences(
                ['A', 'B', 'C'],
                ['Z'],                  # 'Z' can be anywhere
                ['Y', 'C'],             # 'Y' must precede 'C';
                ['A', 'X', 'Y'],        # 'X' must follow 'A' and precede 'Y'
            )
            assert seq == ['A', 'B', 'X', 'Y', 'C', 'Z']
    """
    # we use an OrderedDict to keep elements in order by default
    deps = OrderedDict()                # {item: elems_before_item}
    for iterable in iterables:
        prev = None
        for index, item in enumerate(iterable):
            if not index:
                deps.setdefault(item, [])
            else:
                deps.setdefault(item, []).append(prev)
            prev = item
    return topological_sort(deps)


try:
    import xlwt

    # add some sanitization to respect the excel sheet name restrictions
    # as the sheet name is often translatable, can not control the input
    class PatchedWorkbook(xlwt.Workbook):
        def add_sheet(self, name, cell_overwrite_ok=False):
            # invalid Excel character: []:*?/\
            name = re.sub(r'[\[\]:*?/\\]', '', name)

            # maximum size is 31 characters
            name = name[:31]
            return super(PatchedWorkbook, self).add_sheet(name, cell_overwrite_ok=cell_overwrite_ok)

    xlwt.Workbook = PatchedWorkbook

except ImportError:
    xlwt = None

try:
    import xlsxwriter

    # add some sanitization to respect the excel sheet name restrictions
    # as the sheet name is often translatable, can not control the input
    class PatchedXlsxWorkbook(xlsxwriter.Workbook):

        # TODO when xlsxwriter bump to 0.9.8, add worksheet_class=None parameter instead of kw
        def add_worksheet(self, name=None, **kw):
            if name:
                # invalid Excel character: []:*?/\
                name = re.sub(r'[\[\]:*?/\\]', '', name)

                # maximum size is 31 characters
                name = name[:31]
            return super(PatchedXlsxWorkbook, self).add_worksheet(name, **kw)

    xlsxwriter.Workbook = PatchedXlsxWorkbook

except ImportError:
    xlsxwriter = None


def to_xml(s):
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def get_iso_codes(lang):
    if lang.find('_') != -1:
        if lang.split('_')[0] == lang.split('_')[1].lower():
            lang = lang.split('_')[0]
    return lang

def scan_languages():
    """ Returns all languages supported by OpenERP for translation

    :returns: a list of (lang_code, lang_name) pairs
    :rtype: [(str, unicode)]
    """
    csvpath = odoo.modules.module.get_resource_path('base', 'data', 'res.lang.csv')
    try:
        # read (code, name) from languages in base/data/res.lang.csv
        with open(csvpath, 'rb') as csvfile:
            reader = pycompat.csv_reader(csvfile, delimiter=',', quotechar='"')
            fields = next(reader)
            code_index = fields.index("code")
            name_index = fields.index("name")
            result = [
                (row[code_index], row[name_index])
                for row in reader
            ]
    except Exception:
        _logger.error("Could not read %s", csvpath)
        result = []

    return sorted(result or [('en_US', u'English')], key=itemgetter(1))

def mod10r(number):
    """
    Input number : account or invoice number
    Output return: the same number completed with the recursive mod10
    key
    """
    codec=[0,9,4,6,8,2,7,1,3,5]
    report = 0
    result=""
    for digit in number:
        result += digit
        if digit.isdigit():
            report = codec[ (int(digit) + report) % 10 ]
    return result + str((10 - report) % 10)

def str2bool(s, default=None):
    s = ustr(s).lower()
    y = 'y yes 1 true t on'.split()
    n = 'n no 0 false f off'.split()
    if s not in (y + n):
        if default is None:
            raise ValueError('Use 0/1/yes/no/true/false/on/off')
        return bool(default)
    return s in y

def human_size(sz):
    """
    Return the size in a human readable format
    """
    if not sz:
        return False
    units = ('bytes', 'Kb', 'Mb', 'Gb', 'Tb')
    if isinstance(sz, str):
        sz=len(sz)
    s, i = float(sz), 0
    while s >= 1024 and i < len(units)-1:
        s /= 1024
        i += 1
    return "%0.2f %s" % (s, units[i])

def logged(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        from pprint import pformat

        vector = ['Call -> function: %r' % f]
        for i, arg in enumerate(args):
            vector.append('  arg %02d: %s' % (i, pformat(arg)))
        for key, value in kwargs.items():
            vector.append('  kwarg %10s: %s' % (key, pformat(value)))

        timeb4 = time.time()
        res = f(*args, **kwargs)

        vector.append('  result: %s' % pformat(res))
        vector.append('  time delta: %s' % (time.time() - timeb4))
        _logger.debug('\n'.join(vector))
        return res

    return wrapper

class profile(object):
    def __init__(self, fname=None):
        self.fname = fname

    def __call__(self, f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            profile = cProfile.Profile()
            result = profile.runcall(f, *args, **kwargs)
            profile.dump_stats(self.fname or ("%s.cprof" % (f.__name__,)))
            return result

        return wrapper

def detect_ip_addr():
    """Try a very crude method to figure out a valid external
       IP or hostname for the current machine. Don't rely on this
       for binding to an interface, but it could be used as basis
       for constructing a remote URL to the server.
    """
    def _detect_ip_addr():
        from array import array
        from struct import pack, unpack

        try:
            import fcntl
        except ImportError:
            fcntl = None

        ip_addr = None

        if not fcntl: # not UNIX:
            host = socket.gethostname()
            ip_addr = socket.gethostbyname(host)
        else: # UNIX:
            # get all interfaces:
            nbytes = 128 * 32
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            names = array('B', '\0' * nbytes)
            #print 'names: ', names
            outbytes = unpack('iL', fcntl.ioctl( s.fileno(), 0x8912, pack('iL', nbytes, names.buffer_info()[0])))[0]
            namestr = names.tostring()

            # try 64 bit kernel:
            for i in range(0, outbytes, 40):
                name = namestr[i:i+16].split('\0', 1)[0]
                if name != 'lo':
                    ip_addr = socket.inet_ntoa(namestr[i+20:i+24])
                    break

            # try 32 bit kernel:
            if ip_addr is None:
                ifaces = [namestr[i:i+32].split('\0', 1)[0] for i in range(0, outbytes, 32)]

                for ifname in [iface for iface in ifaces if iface if iface != 'lo']:
                    ip_addr = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, pack('256s', ifname[:15]))[20:24])
                    break

        return ip_addr or 'localhost'

    try:
        ip_addr = _detect_ip_addr()
    except Exception:
        ip_addr = 'localhost'
    return ip_addr

DEFAULT_SERVER_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_SERVER_TIME_FORMAT = "%H:%M:%S"
DEFAULT_SERVER_DATETIME_FORMAT = "%s %s" % (
    DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_TIME_FORMAT)

DATE_LENGTH = len(datetime.date.today().strftime(DEFAULT_SERVER_DATE_FORMAT))

# Python's strftime supports only the format directives
# that are available on the platform's libc, so in order to
# be cross-platform we map to the directives required by
# the C standard (1989 version), always available on platforms
# with a C standard implementation.
DATETIME_FORMATS_MAP = {
        '%C': '', # century
        '%D': '%m/%d/%Y', # modified %y->%Y
        '%e': '%d',
        '%E': '', # special modifier
        '%F': '%Y-%m-%d',
        '%g': '%Y', # modified %y->%Y
        '%G': '%Y',
        '%h': '%b',
        '%k': '%H',
        '%l': '%I',
        '%n': '\n',
        '%O': '', # special modifier
        '%P': '%p',
        '%R': '%H:%M',
        '%r': '%I:%M:%S %p',
        '%s': '', #num of seconds since epoch
        '%T': '%H:%M:%S',
        '%t': ' ', # tab
        '%u': ' %w',
        '%V': '%W',
        '%y': '%Y', # Even if %y works, it's ambiguous, so we should use %Y
        '%+': '%Y-%m-%d %H:%M:%S',

        # %Z is a special case that causes 2 problems at least:
        #  - the timezone names we use (in res_user.context_tz) come
        #    from pytz, but not all these names are recognized by
        #    strptime(), so we cannot convert in both directions
        #    when such a timezone is selected and %Z is in the format
        #  - %Z is replaced by an empty string in strftime() when
        #    there is not tzinfo in a datetime value (e.g when the user
        #    did not pick a context_tz). The resulting string does not
        #    parse back if the format requires %Z.
        # As a consequence, we strip it completely from format strings.
        # The user can always have a look at the context_tz in
        # preferences to check the timezone.
        '%z': '',
        '%Z': '',
}

POSIX_TO_LDML = {
    'a': 'E',
    'A': 'EEEE',
    'b': 'MMM',
    'B': 'MMMM',
    #'c': '',
    'd': 'dd',
    'H': 'HH',
    'I': 'hh',
    'j': 'DDD',
    'm': 'MM',
    'M': 'mm',
    'p': 'a',
    'S': 'ss',
    'U': 'w',
    'w': 'e',
    'W': 'w',
    'y': 'yy',
    'Y': 'yyyy',
    # see comments above, and babel's format_datetime assumes an UTC timezone
    # for naive datetime objects
    #'z': 'Z',
    #'Z': 'z',
}

def posix_to_ldml(fmt, locale):
    """ Converts a posix/strftime pattern into an LDML date format pattern.

    :param fmt: non-extended C89/C90 strftime pattern
    :param locale: babel locale used for locale-specific conversions (e.g. %x and %X)
    :return: unicode
    """
    buf = []
    pc = False
    quoted = []

    for c in fmt:
        # LDML date format patterns uses letters, so letters must be quoted
        if not pc and c.isalpha():
            quoted.append(c if c != "'" else "''")
            continue
        if quoted:
            buf.append("'")
            buf.append(''.join(quoted))
            buf.append("'")
            quoted = []

        if pc:
            if c == '%': # escaped percent
                buf.append('%')
            elif c == 'x': # date format, short seems to match
                buf.append(locale.date_formats['short'].pattern)
            elif c == 'X': # time format, seems to include seconds. short does not
                buf.append(locale.time_formats['medium'].pattern)
            else: # look up format char in static mapping
                buf.append(POSIX_TO_LDML[c])
            pc = False
        elif c == '%':
            pc = True
        else:
            buf.append(c)

    # flush anything remaining in quoted buffer
    if quoted:
        buf.append("'")
        buf.append(''.join(quoted))
        buf.append("'")

    return ''.join(buf)

def split_every(n, iterable, piece_maker=tuple):
    """Splits an iterable into length-n pieces. The last piece will be shorter
       if ``n`` does not evenly divide the iterable length.

       :param int n: maximum size of each generated chunk
       :param Iterable iterable: iterable to chunk into pieces
       :param piece_maker: callable taking an iterable and collecting each
                           chunk from its slice, *must consume the entire slice*.
    """
    iterator = iter(iterable)
    piece = piece_maker(islice(iterator, n))
    while piece:
        yield piece
        piece = piece_maker(islice(iterator, n))

def get_and_group_by_field(cr, uid, obj, ids, field, context=None):
    """ Read the values of ``field´´ for the given ``ids´´ and group ids by value.

       :param string field: name of the field we want to read and group by
       :return: mapping of field values to the list of ids that have it
       :rtype: dict
    """
    res = {}
    for record in obj.read(cr, uid, ids, [field], context=context):
        key = record[field]
        res.setdefault(key[0] if isinstance(key, tuple) else key, []).append(record['id'])
    return res

def get_and_group_by_company(cr, uid, obj, ids, context=None):
    return get_and_group_by_field(cr, uid, obj, ids, field='company_id', context=context)

# port of python 2.6's attrgetter with support for dotted notation
def resolve_attr(obj, attr):
    for name in attr.split("."):
        obj = getattr(obj, name)
    return obj

def attrgetter(*items):
    if len(items) == 1:
        attr = items[0]
        def g(obj):
            return resolve_attr(obj, attr)
    else:
        def g(obj):
            return tuple(resolve_attr(obj, attr) for attr in items)
    return g

def discardattr(obj, key):
    """ Perform a ``delattr(obj, key)`` but without crashing if ``key`` is not present. """
    try:
        delattr(obj, key)
    except AttributeError:
        pass

# ---------------------------------------------
# String management
# ---------------------------------------------

# Inspired by http://stackoverflow.com/questions/517923
def remove_accents(input_str):
    """Suboptimal-but-better-than-nothing way to replace accented
    latin letters by an ASCII equivalent. Will obviously change the
    meaning of input_str and work only for some cases"""
    if not input_str:
        return input_str
    input_str = ustr(input_str)
    nkfd_form = unicodedata.normalize('NFKD', input_str)
    return u''.join([c for c in nkfd_form if not unicodedata.combining(c)])

class unquote(str):
    """A subclass of str that implements repr() without enclosing quotation marks
       or escaping, keeping the original string untouched. The name come from Lisp's unquote.
       One of the uses for this is to preserve or insert bare variable names within dicts during eval()
       of a dict's repr(). Use with care.

       Some examples (notice that there are never quotes surrounding
       the ``active_id`` name:

       >>> unquote('active_id')
       active_id
       >>> d = {'test': unquote('active_id')}
       >>> d
       {'test': active_id}
       >>> print d
       {'test': active_id}
    """
    def __repr__(self):
        return self

class UnquoteEvalContext(defaultdict):
    """Defaultdict-based evaluation context that returns
       an ``unquote`` string for any missing name used during
       the evaluation.
       Mostly useful for evaluating OpenERP domains/contexts that
       may refer to names that are unknown at the time of eval,
       so that when the context/domain is converted back to a string,
       the original names are preserved.

       **Warning**: using an ``UnquoteEvalContext`` as context for ``eval()`` or
       ``safe_eval()`` will shadow the builtins, which may cause other
       failures, depending on what is evaluated.

       Example (notice that ``section_id`` is preserved in the final
       result) :

       >>> context_str = "{'default_user_id': uid, 'default_section_id': section_id}"
       >>> eval(context_str, UnquoteEvalContext(uid=1))
       {'default_user_id': 1, 'default_section_id': section_id}

       """
    def __init__(self, *args, **kwargs):
        super(UnquoteEvalContext, self).__init__(None, *args, **kwargs)

    def __missing__(self, key):
        return unquote(key)


class mute_logger(object):
    """Temporary suppress the logging.
    Can be used as context manager or decorator.

        @mute_logger('odoo.plic.ploc')
        def do_stuff():
            blahblah()

        with mute_logger('odoo.foo.bar'):
            do_suff()

    """
    def __init__(self, *loggers):
        self.loggers = loggers

    def filter(self, record):
        return 0

    def __enter__(self):
        for logger in self.loggers:
            assert isinstance(logger, str),\
                "A logger name must be a string, got %s" % type(logger)
            logging.getLogger(logger).addFilter(self)

    def __exit__(self, exc_type=None, exc_val=None, exc_tb=None):
        for logger in self.loggers:
            logging.getLogger(logger).removeFilter(self)

    def __call__(self, func):
        @wraps(func)
        def deco(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return deco

_ph = object()
class CountingStream(object):
    """ Stream wrapper counting the number of element it has yielded. Similar
    role to ``enumerate``, but for use when the iteration process of the stream
    isn't fully under caller control (the stream can be iterated from multiple
    points including within a library)

    ``start`` allows overriding the starting index (the index before the first
    item is returned).

    On each iteration (call to :meth:`~.next`), increases its :attr:`~.index`
    by one.

    .. attribute:: index

        ``int``, index of the last yielded element in the stream. If the stream
        has ended, will give an index 1-past the stream
    """
    def __init__(self, stream, start=-1):
        self.stream = iter(stream)
        self.index = start
        self.stopped = False
    def __iter__(self):
        return self
    def next(self):
        if self.stopped: raise StopIteration()
        self.index += 1
        val = next(self.stream, _ph)
        if val is _ph:
            self.stopped = True
            raise StopIteration()
        return val
    __next__ = next

def stripped_sys_argv(*strip_args):
    """Return sys.argv with some arguments stripped, suitable for reexecution or subprocesses"""
    strip_args = sorted(set(strip_args) | set(['-s', '--save', '-u', '--update', '-i', '--init', '--i18n-overwrite']))
    assert all(config.parser.has_option(s) for s in strip_args)
    takes_value = dict((s, config.parser.get_option(s).takes_value()) for s in strip_args)

    longs, shorts = list(tuple(y) for _, y in itergroupby(strip_args, lambda x: x.startswith('--')))
    longs_eq = tuple(l + '=' for l in longs if takes_value[l])

    args = sys.argv[:]

    def strip(args, i):
        return args[i].startswith(shorts) \
            or args[i].startswith(longs_eq) or (args[i] in longs) \
            or (i >= 1 and (args[i - 1] in strip_args) and takes_value[args[i - 1]])

    return [x for i, x in enumerate(args) if not strip(args, i)]

class ConstantMapping(Mapping):
    """
    An immutable mapping returning the provided value for every single key.

    Useful for default value to methods
    """
    __slots__ = ['_value']
    def __init__(self, val):
        self._value = val

    def __len__(self):
        """
        defaultdict updates its length for each individually requested key, is
        that really useful?
        """
        return 0

    def __iter__(self):
        """
        same as len, defaultdict updates its iterable keyset with each key
        requested, is there a point for this?
        """
        return iter([])

    def __getitem__(self, item):
        return self._value


def dumpstacks(sig=None, frame=None, thread_idents=None):
    """ Signal handler: dump a stack trace for each existing thread or given
    thread(s) specified through the ``thread_idents`` sequence.
    """
    code = []

    def extract_stack(stack):
        for filename, lineno, name, line in traceback.extract_stack(stack):
            yield 'File: "%s", line %d, in %s' % (filename, lineno, name)
            if line:
                yield "  %s" % (line.strip(),)

    # code from http://stackoverflow.com/questions/132058/getting-stack-trace-from-a-running-python-application#answer-2569696
    # modified for python 2.5 compatibility
    threads_info = {th.ident: {'repr': repr(th),
                               'uid': getattr(th, 'uid', 'n/a'),
                               'dbname': getattr(th, 'dbname', 'n/a'),
                               'url': getattr(th, 'url', 'n/a')}
                    for th in threading.enumerate()}
    for threadId, stack in sys._current_frames().items():
        if not thread_idents or threadId in thread_idents:
            thread_info = threads_info.get(threadId, {})
            code.append("\n# Thread: %s (db:%s) (uid:%s) (url:%s)" %
                        (thread_info.get('repr', threadId),
                         thread_info.get('dbname', 'n/a'),
                         thread_info.get('uid', 'n/a'),
                         thread_info.get('url', 'n/a')))
            for line in extract_stack(stack):
                code.append(line)

    if odoo.evented:
        # code from http://stackoverflow.com/questions/12510648/in-gevent-how-can-i-dump-stack-traces-of-all-running-greenlets
        import gc
        from greenlet import greenlet
        for ob in gc.get_objects():
            if not isinstance(ob, greenlet) or not ob:
                continue
            code.append("\n# Greenlet: %r" % (ob,))
            for line in extract_stack(ob.gr_frame):
                code.append(line)

    _logger.info("\n".join(code))

def freehash(arg):
    try:
        return hash(arg)
    except Exception:
        if isinstance(arg, Mapping):
            return hash(frozendict(arg))
        elif isinstance(arg, Iterable):
            return hash(frozenset(freehash(item) for item in arg))
        else:
            return id(arg)

def clean_context(context):
    """ This function take a dictionary and remove each entry with its key starting with 'default_' """
    return {k: v for k, v in context.items() if not k.startswith('default_')}


class frozendict(dict):
    """ An implementation of an immutable dictionary. """
    __slots__ = ()

    def __delitem__(self, key):
        raise NotImplementedError("'__delitem__' not supported on frozendict")

    def __setitem__(self, key, val):
        raise NotImplementedError("'__setitem__' not supported on frozendict")

    def clear(self):
        raise NotImplementedError("'clear' not supported on frozendict")

    def pop(self, key, default=None):
        raise NotImplementedError("'pop' not supported on frozendict")

    def popitem(self):
        raise NotImplementedError("'popitem' not supported on frozendict")

    def setdefault(self, key, default=None):
        raise NotImplementedError("'setdefault' not supported on frozendict")

    def update(self, *args, **kwargs):
        raise NotImplementedError("'update' not supported on frozendict")

    def __hash__(self):
        return hash(frozenset((key, freehash(val)) for key, val in self.items()))


class Collector(dict):
    """ A mapping from keys to tuples.  This implements a relation, and can be
        seen as a space optimization for ``defaultdict(tuple)``.
    """
    __slots__ = ()

    def __getitem__(self, key):
        return self.get(key, ())

    def __setitem__(self, key, val):
        val = tuple(val)
        if val:
            super().__setitem__(key, val)
        else:
            super().pop(key, None)

    def add(self, key, val):
        vals = self[key]
        if val not in vals:
            self[key] = vals + (val,)

    def discard_keys_and_values(self, excludes):
        for key in excludes:
            self.pop(key, None)
        for key, vals in list(self.items()):
            self[key] = tuple(val for val in vals if val not in excludes)


class StackMap(MutableMapping):
    """ A stack of mappings behaving as a single mapping, and used to implement
        nested scopes. The lookups search the stack from top to bottom, and
        returns the first value found. Mutable operations modify the topmost
        mapping only.
    """
    __slots__ = ['_maps']

    def __init__(self, m=None):
        self._maps = [] if m is None else [m]

    def __getitem__(self, key):
        for mapping in reversed(self._maps):
            try:
                return mapping[key]
            except KeyError:
                pass
        raise KeyError(key)

    def __setitem__(self, key, val):
        self._maps[-1][key] = val

    def __delitem__(self, key):
        del self._maps[-1][key]

    def __iter__(self):
        return iter({key for mapping in self._maps for key in mapping})

    def __len__(self):
        return sum(1 for key in self)

    def __str__(self):
        return u"<StackMap %s>" % self._maps

    def pushmap(self, m=None):
        self._maps.append({} if m is None else m)

    def popmap(self):
        return self._maps.pop()


class OrderedSet(MutableSet):
    """ A set collection that remembers the elements first insertion order. """
    __slots__ = ['_map']

    def __init__(self, elems=()):
        self._map = dict.fromkeys(elems)

    def __contains__(self, elem):
        return elem in self._map

    def __iter__(self):
        return iter(self._map)

    def __len__(self):
        return len(self._map)

    def add(self, elem):
        self._map[elem] = None

    def discard(self, elem):
        self._map.pop(elem, None)

    def update(self, elems):
        self._map.update(zip(elems, itertools.repeat(None)))

    def difference_update(self, elems):
        for elem in elems:
            self.discard(elem)

    def __repr__(self):
        return f'{type(self).__name__}({list(self)!r})'


class LastOrderedSet(OrderedSet):
    """ A set collection that remembers the elements last insertion order. """
    def add(self, elem):
        OrderedSet.discard(self, elem)
        OrderedSet.add(self, elem)


class Callbacks:
    """ A simple queue of callback functions.  Upon run, every function is
    called (in addition order), and the queue is emptied.

        callbacks = Callbacks()

        # add foo
        def foo():
            print("foo")

        callbacks.add(foo)

        # add bar
        callbacks.add
        def bar():
            print("bar")

        # add foo again
        callbacks.add(foo)

        # call foo(), bar(), foo(), then clear the callback queue
        callbacks.run()

    The queue also provides a ``data`` dictionary, that may be freely used to
    store anything, but is mostly aimed at aggregating data for callbacks.  The
    dictionary is automatically cleared by ``run()`` once all callback functions
    have been called.

        # register foo to process aggregated data
        @callbacks.add
        def foo():
            print(sum(callbacks.data['foo']))

        callbacks.data.setdefault('foo', []).append(1)
        ...
        callbacks.data.setdefault('foo', []).append(2)
        ...
        callbacks.data.setdefault('foo', []).append(3)

        # call foo(), which prints 6
        callbacks.run()

    Given the global nature of ``data``, the keys should identify in a unique
    way the data being stored.  It is recommended to use strings with a
    structure like ``"{module}.{feature}"``.
    """
    __slots__ = ['_funcs', 'data']

    def __init__(self):
        self._funcs = collections.deque()
        self.data = {}

    def add(self, func):
        """ Add the given function. """
        self._funcs.append(func)

    def run(self):
        """ Call all the functions (in addition order), then clear associated data.
        """
        while self._funcs:
            func = self._funcs.popleft()
            func()
        self.clear()

    def clear(self):
        """ Remove all callbacks and data from self. """
        self._funcs.clear()
        self.data.clear()


class IterableGenerator:
    """ An iterable object based on a generator function, which is called each
        time the object is iterated over.
    """
    __slots__ = ['func', 'args']

    def __init__(self, func, *args):
        self.func = func
        self.args = args

    def __iter__(self):
        return self.func(*self.args)


def groupby(iterable, key=None):
    """ Return a collection of pairs ``(key, elements)`` from ``iterable``. The
        ``key`` is a function computing a key value for each element. This
        function is similar to ``itertools.groupby``, but aggregates all
        elements under the same key, not only consecutive elements.
    """
    if key is None:
        key = lambda arg: arg
    groups = defaultdict(list)
    for elem in iterable:
        groups[key(elem)].append(elem)
    return groups.items()

def unique(it):
    """ "Uniquifier" for the provided iterable: will output each element of
    the iterable once.

    The iterable's elements must be hashahble.

    :param Iterable it:
    :rtype: Iterator
    """
    seen = set()
    for e in it:
        if e not in seen:
            seen.add(e)
            yield e

class Reverse(object):
    """ Wraps a value and reverses its ordering, useful in key functions when
    mixing ascending and descending sort on non-numeric data as the
    ``reverse`` parameter can not do piecemeal reordering.
    """
    __slots__ = ['val']

    def __init__(self, val):
        self.val = val

    def __eq__(self, other): return self.val == other.val
    def __ne__(self, other): return self.val != other.val

    def __ge__(self, other): return self.val <= other.val
    def __gt__(self, other): return self.val < other.val
    def __le__(self, other): return self.val >= other.val
    def __lt__(self, other): return self.val > other.val

@contextmanager
def ignore(*exc):
    try:
        yield
    except exc:
        pass

html_escape = markupsafe.escape

def get_lang(env, lang_code=False):
    """
    Retrieve the first lang object installed, by checking the parameter lang_code,
    the context and then the company. If no lang is installed from those variables,
    fallback on the first lang installed in the system.
    :param str lang_code: the locale (i.e. en_US)
    :return res.lang: the first lang found that is installed on the system.
    """
    langs = [code for code, _ in env['res.lang'].get_installed()]
    lang = langs[0]
    if lang_code and lang_code in langs:
        lang = lang_code
    elif env.context.get('lang') in langs:
        lang = env.context.get('lang')
    elif env.user.company_id.partner_id.lang in langs:
        lang = env.user.company_id.partner_id.lang
    return env['res.lang']._lang_get(lang)

def babel_locale_parse(lang_code):
    try:
        return babel.Locale.parse(lang_code)
    except:
        try:
            return babel.Locale.default()
        except:
            return babel.Locale.parse("en_US")

def formatLang(env, value, digits=None, grouping=True, monetary=False, dp=False, currency_obj=False):
    """
        Assuming 'Account' decimal.precision=3:
            formatLang(value) -> digits=2 (default)
            formatLang(value, digits=4) -> digits=4
            formatLang(value, dp='Account') -> digits=3
            formatLang(value, digits=5, dp='Account') -> digits=5
    """

    if digits is None:
        digits = DEFAULT_DIGITS = 2
        if dp:
            decimal_precision_obj = env['decimal.precision']
            digits = decimal_precision_obj.precision_get(dp)
        elif currency_obj:
            digits = currency_obj.decimal_places

    if isinstance(value, str) and not value:
        return ''

    lang_obj = get_lang(env)

    res = lang_obj.format('%.' + str(digits) + 'f', value, grouping=grouping, monetary=monetary)

    if currency_obj and currency_obj.symbol:
        if currency_obj.position == 'after':
            res = '%s%s%s' % (res, NON_BREAKING_SPACE, currency_obj.symbol)
        elif currency_obj and currency_obj.position == 'before':
            res = '%s%s%s' % (currency_obj.symbol, NON_BREAKING_SPACE, res)
    return res


def format_date(env, value, lang_code=False, date_format=False):
    '''
        Formats the date in a given format.

        :param env: an environment.
        :param date, datetime or string value: the date to format.
        :param string lang_code: the lang code, if not specified it is extracted from the
            environment context.
        :param string date_format: the format or the date (LDML format), if not specified the
            default format of the lang.
        :return: date formatted in the specified format.
        :rtype: string
    '''
    if not value:
        return ''
    if isinstance(value, str):
        if len(value) < DATE_LENGTH:
            return ''
        if len(value) > DATE_LENGTH:
            # a datetime, convert to correct timezone
            value = odoo.fields.Datetime.from_string(value)
            value = odoo.fields.Datetime.context_timestamp(env['res.lang'], value)
        else:
            value = odoo.fields.Datetime.from_string(value)

    lang = get_lang(env, lang_code)
    locale = babel_locale_parse(lang.code)
    if not date_format:
        date_format = posix_to_ldml(lang.date_format, locale=locale)

    return babel.dates.format_date(value, format=date_format, locale=locale)

def parse_date(env, value, lang_code=False):
    '''
        Parse the date from a given format. If it is not a valid format for the
        localization, return the original string.

        :param env: an environment.
        :param string value: the date to parse.
        :param string lang_code: the lang code, if not specified it is extracted from the
            environment context.
        :return: date object from the localized string
        :rtype: datetime.date
    '''
    lang = get_lang(env, lang_code)
    locale = babel_locale_parse(lang.code)
    try:
        return babel.dates.parse_date(value, locale=locale)
    except:
        return value


def format_datetime(env, value, tz=False, dt_format='medium', lang_code=False):
    """ Formats the datetime in a given format.

        :param {str, datetime} value: naive datetime to format either in string or in datetime
        :param {str} tz: name of the timezone  in which the given datetime should be localized
        :param {str} dt_format: one of “full”, “long”, “medium”, or “short”, or a custom date/time pattern compatible with `babel` lib
        :param {str} lang_code: ISO code of the language to use to render the given datetime
    """
    if not value:
        return ''
    if isinstance(value, str):
        timestamp = odoo.fields.Datetime.from_string(value)
    else:
        timestamp = value

    tz_name = tz or env.user.tz or 'UTC'
    utc_datetime = pytz.utc.localize(timestamp, is_dst=False)
    try:
        context_tz = pytz.timezone(tz_name)
        localized_datetime = utc_datetime.astimezone(context_tz)
    except Exception:
        localized_datetime = utc_datetime

    lang = get_lang(env, lang_code)

    locale = babel_locale_parse(lang.code or lang_code)  # lang can be inactive, so `lang`is empty
    if not dt_format:
        date_format = posix_to_ldml(lang.date_format, locale=locale)
        time_format = posix_to_ldml(lang.time_format, locale=locale)
        dt_format = '%s %s' % (date_format, time_format)

    # Babel allows to format datetime in a specific language without change locale
    # So month 1 = January in English, and janvier in French
    # Be aware that the default value for format is 'medium', instead of 'short'
    #     medium:  Jan 5, 2016, 10:20:31 PM |   5 janv. 2016 22:20:31
    #     short:   1/5/16, 10:20 PM         |   5/01/16 22:20
    # Formatting available here : http://babel.pocoo.org/en/latest/dates.html#date-fields
    return babel.dates.format_datetime(localized_datetime, dt_format, locale=locale)


def format_time(env, value, tz=False, time_format='medium', lang_code=False):
    """ Format the given time (hour, minute and second) with the current user preference (language, format, ...)

        :param value: the time to format
        :type value: `datetime.time` instance. Could be timezoned to display tzinfo according to format (e.i.: 'full' format)
        :param tz: name of the timezone  in which the given datetime should be localized
        :param time_format: one of “full”, “long”, “medium”, or “short”, or a custom time pattern
        :param lang_code: ISO

        :rtype str
    """
    if not value:
        return ''

    if isinstance(value, datetime.time):
        localized_datetime = value
    else:
        if isinstance(value, str):
            value = odoo.fields.Datetime.from_string(value)
        tz_name = tz or env.user.tz or 'UTC'
        utc_datetime = pytz.utc.localize(value, is_dst=False)
        try:
            context_tz = pytz.timezone(tz_name)
            localized_datetime = utc_datetime.astimezone(context_tz)
        except Exception:
            localized_datetime = utc_datetime

    lang = get_lang(env, lang_code)
    locale = babel_locale_parse(lang.code)
    if not time_format:
        time_format = posix_to_ldml(lang.time_format, locale=locale)

    return babel.dates.format_time(localized_datetime, format=time_format, locale=locale)


def _format_time_ago(env, time_delta, lang_code=False, add_direction=True):
    if not lang_code:
        langs = [code for code, _ in env['res.lang'].get_installed()]
        lang_code = env.context['lang'] if env.context.get('lang') in langs else (env.user.company_id.partner_id.lang or langs[0])
    locale = babel_locale_parse(lang_code)
    return babel.dates.format_timedelta(-time_delta, add_direction=add_direction, locale=locale)


def format_decimalized_number(number, decimal=1):
    """Format a number to display to nearest metrics unit next to it.

    Do not display digits if all visible digits are null.
    Do not display units higher then "Tera" because most of people don't know what
    a "Yotta" is.

    >>> format_decimalized_number(123_456.789)
    123.5k
    >>> format_decimalized_number(123_000.789)
    123k
    >>> format_decimalized_number(-123_456.789)
    -123.5k
    >>> format_decimalized_number(0.789)
    0.8
    """
    for unit in ['', 'k', 'M', 'G']:
        if abs(number) < 1000.0:
            return "%g%s" % (round(number, decimal), unit)
        number /= 1000.0
    return "%g%s" % (round(number, decimal), 'T')


def format_decimalized_amount(amount, currency=None):
    """Format a amount to display the currency and also display the metric unit of the amount.

    >>> format_decimalized_amount(123_456.789, res.currency("$"))
    $123.5k
    """
    formated_amount = format_decimalized_number(amount)

    if not currency:
        return formated_amount

    if currency.position == 'before':
        return "%s%s" % (currency.symbol or '', formated_amount)

    return "%s %s" % (formated_amount, currency.symbol or '')


def format_amount(env, amount, currency, lang_code=False):
    fmt = "%.{0}f".format(currency.decimal_places)
    lang = get_lang(env, lang_code)

    formatted_amount = lang.format(fmt, currency.round(amount), grouping=True, monetary=True)\
        .replace(r' ', u'\N{NO-BREAK SPACE}').replace(r'-', u'-\N{ZERO WIDTH NO-BREAK SPACE}')

    pre = post = u''
    if currency.position == 'before':
        pre = u'{symbol}\N{NO-BREAK SPACE}'.format(symbol=currency.symbol or '')
    else:
        post = u'\N{NO-BREAK SPACE}{symbol}'.format(symbol=currency.symbol or '')

    return u'{pre}{0}{post}'.format(formatted_amount, pre=pre, post=post)


def format_duration(value):
    """ Format a float: used to display integral or fractional values as
        human-readable time spans (e.g. 1.5 as "01:30").
    """
    hours, minutes = divmod(abs(value) * 60, 60)
    minutes = round(minutes)
    if minutes == 60:
        minutes = 0
        hours += 1
    if value < 0:
        return '-%02d:%02d' % (hours, minutes)
    return '%02d:%02d' % (hours, minutes)


def _consteq(str1, str2):
    """ Constant-time string comparison. Suitable to compare bytestrings of fixed,
        known length only, because length difference is optimized. """
    return len(str1) == len(str2) and sum(ord(x)^ord(y) for x, y in zip(str1, str2)) == 0

consteq = getattr(passlib.utils, 'consteq', _consteq)

# forbid globals entirely: str/unicode, int/long, float, bool, tuple, list, dict, None
class Unpickler(pickle_.Unpickler, object):
    find_global = None # Python 2
    find_class = None # Python 3
def _pickle_load(stream, encoding='ASCII', errors=False):
    if sys.version_info[0] == 3:
        unpickler = Unpickler(stream, encoding=encoding)
    else:
        unpickler = Unpickler(stream)
    try:
        return unpickler.load()
    except Exception:
        _logger.warning('Failed unpickling data, returning default: %r',
                        errors, exc_info=True)
        return errors
pickle = types.ModuleType(__name__ + '.pickle')
pickle.load = _pickle_load
pickle.loads = lambda text, encoding='ASCII': _pickle_load(io.BytesIO(text), encoding=encoding)
pickle.dump = pickle_.dump
pickle.dumps = pickle_.dumps


class ReadonlyDict(Mapping):
    """Helper for an unmodifiable dictionary, not even updatable using `dict.update`.

    This is similar to a `frozendict`, with one drawback and one advantage:

    - `dict.update` works for a `frozendict` but not for a `ReadonlyDict`.
    - `json.dumps` works for a `frozendict` by default but not for a `ReadonlyDict`.

    This comes from the fact `frozendict` inherits from `dict`
    while `ReadonlyDict` inherits from `collections.abc.Mapping`.

    So, depending on your needs,
    whether you absolutely must prevent the dictionary from being updated (e.g., for security reasons)
    or you require it to be supported by `json.dumps`, you can choose either option.

        E.g.
          data = ReadonlyDict({'foo': 'bar'})
          data['baz'] = 'xyz' # raises exception
          data.update({'baz', 'xyz'}) # raises exception
          dict.update(data, {'baz': 'xyz'}) # raises exception
    """
    def __init__(self, data):
        self.__data = dict(data)

    def __getitem__(self, key):
        return self.__data[key]

    def __len__(self):
        return len(self.__data)

    def __iter__(self):
        return iter(self.__data)


class DotDict(dict):
    """Helper for dot.notation access to dictionary attributes

        E.g.
          foo = DotDict({'bar': False})
          return foo.bar
    """
    def __getattr__(self, attrib):
        val = self.get(attrib)
        return DotDict(val) if isinstance(val, dict) else val


def get_diff(data_from, data_to, custom_style=False):
    """
    Return, in an HTML table, the diff between two texts.

    :param tuple data_from: tuple(text, name), name will be used as table header
    :param tuple data_to: tuple(text, name), name will be used as table header
    :param tuple custom_style: string, style css including <style> tag.
    :return: a string containing the diff in an HTML table format.
    """
    def handle_style(html_diff, custom_style):
        """ The HtmlDiff lib will add some useful classes on the DOM to
        identify elements. Simply append to those classes some BS4 ones.
        For the table to fit the modal width, some custom style is needed.
        """
        to_append = {
            'diff_header': 'bg-600 text-center align-top px-2',
            'diff_next': 'd-none',
        }
        for old, new in to_append.items():
            html_diff = html_diff.replace(old, "%s %s" % (old, new))
        html_diff = html_diff.replace('nowrap', '')
        html_diff += custom_style or '''
            <style>
                .modal-dialog.modal-lg:has(table.diff) {
                    max-width: 1600px;
                    padding-left: 1.75rem;
                    padding-right: 1.75rem;
                }
                table.diff { width: 100%; }
                table.diff th.diff_header { width: 50%; }
                table.diff td.diff_header { white-space: nowrap; }
                table.diff td { word-break: break-all; vertical-align: top; }
                table.diff .diff_chg, table.diff .diff_sub, table.diff .diff_add {
                    display: inline-block;
                    color: inherit;
                }
                table.diff .diff_sub, table.diff td:nth-child(3) > .diff_chg { background-color: #ffc1c0; }
                table.diff .diff_add, table.diff td:nth-child(6) > .diff_chg { background-color: #abf2bc; }
                table.diff td:nth-child(3):has(>.diff_chg, .diff_sub) { background-color: #ffebe9; }
                table.diff td:nth-child(6):has(>.diff_chg, .diff_add) { background-color: #e6ffec; }
            </style>
        '''
        return html_diff

    diff = HtmlDiff(tabsize=2).make_table(
        data_from[0].splitlines(),
        data_to[0].splitlines(),
        data_from[1],
        data_to[1],
        context=True,  # Show only diff lines, not all the code
        numlines=3,
    )
    return handle_style(diff, custom_style)


def traverse_containers(val, type_):
    """ Yields atoms filtered by specified type_ (or type tuple), traverses
    through standard containers (non-string mappings or sequences) *unless*
    they're selected by the type filter
    """
    from odoo.models import BaseModel
    if isinstance(val, type_):
        yield val
    elif isinstance(val, (str, bytes, BaseModel)):
        return
    elif isinstance(val, Mapping):
        for k, v in val.items():
            yield from traverse_containers(k, type_)
            yield from traverse_containers(v, type_)
    elif isinstance(val, collections.abc.Sequence):
        for v in val:
            yield from traverse_containers(v, type_)


def hmac(env, scope, message, hash_function=hashlib.sha256):
    """Compute HMAC with `database.secret` config parameter as key.

    :param env: sudo environment to use for retrieving config parameter
    :param message: message to authenticate
    :param scope: scope of the authentication, to have different signature for the same
        message in different usage
    :param hash_function: hash function to use for HMAC (default: SHA-256)
    """
    if not scope:
        raise ValueError('Non-empty scope required')

    secret = env['ir.config_parameter'].get_param('database.secret')
    message = repr((scope, message))
    return hmac_lib.new(
        secret.encode(),
        message.encode(),
        hash_function,
    ).hexdigest()
