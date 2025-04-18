# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Some functions related to the os and os.path module
"""
import logging
import os
import re
import tempfile
import zipfile

from contextlib import contextmanager
from os.path import join as opj

_logger = logging.getLogger(__name__)

WINDOWS_RESERVED = re.compile(r'''
    ^
    # forbidden stems: reserved keywords
    (:?CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])
    # even with an extension this is recommended against
    (:?\..*)?
    $
''', flags=re.IGNORECASE | re.VERBOSE)
def clean_filename(name, replacement=''):
    """ Strips or replaces possibly problematic or annoying characters our of
    the input string, in order to make it a valid filename in most operating
    systems (including dropping reserved Windows filenames).

    If this results in an empty string, results in "Untitled" (localized).

    Allows:

    * any alphanumeric character (unicode)
    * underscore (_) as that's innocuous
    * dot (.) except in leading position to avoid creating dotfiles
    * dash (-) except in leading position to avoid annoyance / confusion with
      command options
    * brackets ([ and ]), while they correspond to shell *character class*
      they're a common way to mark / tag files especially on windows
    * parenthesis ("(" and ")"), a more natural though less common version of
      the former
    * space (" ")

    :param str name: file name to clean up
    :param str replacement:
        replacement string to use for sequences of problematic input, by default
        an empty string to remove them entirely, each contiguous sequence of
        problems is replaced by a single replacement
    :rtype: str
    """
    if WINDOWS_RESERVED.match(name):
        return "Untitled"
    return re.sub(r'[^\w_.()\[\] -]+', replacement, name).lstrip('.-') or "Untitled"

def listdir(dir, recursive=False):
    """Allow to recursively get the file listing following symlinks, returns
    paths relative to the provided `dir` except completely broken if the symlink
    it follows leaves `dir`...
    """
    if not recursive:
        _logger.getChild('listdir').warning("Deprecated: just call os.listdir...")
    dir = os.path.normpath(dir)
    if not recursive:
        return os.listdir(dir)

    res = []
    for root, _, files in os.walk(dir, followlinks=True):
        r = os.path.relpath(root, dir)
        # FIXME: what should happen if root is outside dir?
        yield from (opj(r, f) for f in files)
    return res

def walksymlinks(top, topdown=True, onerror=None):
    _logger.getChild('walksymlinks').warning("Deprecated: use os.walk(followlinks=True) instead")
    return os.walk(top, topdown=topdown, onerror=onerror, followlinks=True)

@contextmanager
def tempdir():
    _logger.getChild('tempdir').warning("Deprecated: use tempfile.TemporaryDirectory")
    with tempfile.TemporaryDirectory() as d:
        yield d

def zip_dir(path, stream, include_dir=True, fnct_sort=None):      # TODO add ignore list
    """
    : param fnct_sort : Function to be passed to "key" parameter of built-in
                        python sorted() to provide flexibility of sorting files
                        inside ZIP archive according to specific requirements.
    """
    path = os.path.normpath(path)
    len_prefix = len(os.path.dirname(path)) if include_dir else len(path)
    if len_prefix:
        len_prefix += 1

    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
        for dirpath, dirnames, filenames in os.walk(path):
            filenames = sorted(filenames, key=fnct_sort)
            for fname in filenames:
                bname, ext = os.path.splitext(fname)
                ext = ext or bname
                if ext not in ['.pyc', '.pyo', '.swp', '.DS_Store']:
                    path = os.path.normpath(os.path.join(dirpath, fname))
                    if os.path.isfile(path):
                        zipf.write(path, path[len_prefix:])


if os.name != 'nt':
    getppid = os.getppid
    is_running_as_nt_service = lambda: False
else:
    import ctypes
    import win32service as ws
    import win32serviceutil as wsu

    # based on http://mail.python.org/pipermail/python-win32/2007-June/006174.html
    _TH32CS_SNAPPROCESS = 0x00000002
    class _PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_ulong),
                    ("cntUsage", ctypes.c_ulong),
                    ("th32ProcessID", ctypes.c_ulong),
                    ("th32DefaultHeapID", ctypes.c_ulong),
                    ("th32ModuleID", ctypes.c_ulong),
                    ("cntThreads", ctypes.c_ulong),
                    ("th32ParentProcessID", ctypes.c_ulong),
                    ("pcPriClassBase", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong),
                    ("szExeFile", ctypes.c_char * 260)]

    def getppid():
        CreateToolhelp32Snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot
        Process32First = ctypes.windll.kernel32.Process32First
        Process32Next = ctypes.windll.kernel32.Process32Next
        CloseHandle = ctypes.windll.kernel32.CloseHandle
        hProcessSnap = CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        current_pid = os.getpid()
        try:
            pe32 = _PROCESSENTRY32()
            pe32.dwSize = ctypes.sizeof(_PROCESSENTRY32)
            if not Process32First(hProcessSnap, ctypes.byref(pe32)):
                raise OSError('Failed getting first process.')
            while True:
                if pe32.th32ProcessID == current_pid:
                    return pe32.th32ParentProcessID
                if not Process32Next(hProcessSnap, ctypes.byref(pe32)):
                    return None
        finally:
            CloseHandle(hProcessSnap)

    from contextlib import contextmanager
    from odoo.release import nt_service_name

    def is_running_as_nt_service():
        @contextmanager
        def close_srv(srv):
            try:
                yield srv
            finally:
                ws.CloseServiceHandle(srv)

        try:
            with close_srv(ws.OpenSCManager(None, None, ws.SC_MANAGER_ALL_ACCESS)) as hscm:
                with close_srv(wsu.SmartOpenService(hscm, nt_service_name, ws.SERVICE_ALL_ACCESS)) as hs:
                    info = ws.QueryServiceStatusEx(hs)
                    return info['ProcessId'] == getppid()
        except Exception:
            return False

if __name__ == '__main__':
    from pprint import pprint as pp
    pp(listdir('../report', True))
