# -*- coding: utf-8 -*-
#----------------------------------------------------------
# OpenERP HTTP layer
#----------------------------------------------------------
import ast
import cgi
import collections
import contextlib
import functools
import hashlib
import hmac
import inspect
import logging
import mimetypes
import os
import pprint
import random
import re
import sys
import threading
import time
import traceback
import warnings
from os.path import join as opj
from zlib import adler32

import babel.core
from datetime import datetime
import passlib.utils
import psycopg2
import json
import werkzeug.datastructures
import werkzeug.exceptions
import werkzeug.local
import werkzeug.routing
import werkzeug.wrappers
from werkzeug import urls
from werkzeug.wsgi import wrap_file
try:
    from werkzeug.middleware.shared_data import SharedDataMiddleware
except ImportError:
    from werkzeug.wsgi import SharedDataMiddleware

try:
    import psutil
except ImportError:
    psutil = None

import odoo
from .service.server import memory_info
from .service import security, model as service_model
from .tools.func import lazy_property
from .tools import profiler
from .tools import ustr, consteq, frozendict, pycompat, unique, date_utils
from .tools.mimetypes import guess_mimetype
from .tools.misc import str2bool
from .tools._vendor import sessions
from .tools._vendor.useragents import UserAgent
from .modules.module import read_manifest

_logger = logging.getLogger(__name__)
rpc_request = logging.getLogger(__name__ + '.rpc.request')
rpc_response = logging.getLogger(__name__ + '.rpc.response')

# One week cache for static content (static files in apps, library files, ...)
# Safe resources may use what google page speed recommends (1 year)
# (attachments with unique hash in the URL, ...)
STATIC_CACHE = 3600 * 24 * 7
STATIC_CACHE_LONG = 3600 * 24 * 365

# To remove when corrected in Babel
babel.core.LOCALE_ALIASES['nb'] = 'nb_NO'

""" Debug mode is stored in session and should always be a string.
    It can be activated with an URL query string `debug=<mode>` where
    mode is either:
    - 'tests' to load tests assets
    - 'assets' to load assets non minified
    - any other truthy value to enable simple debug mode (to show some
      technical feature, to show complete traceback in frontend error..)
    - any falsy value to disable debug mode

    You can use any truthy/falsy value from `str2bool` (eg: 'on', 'f'..)
    Multiple debug modes can be activated simultaneously, separated with
    a comma (eg: 'tests, assets').
"""
ALLOWED_DEBUG_MODES = ['', '1', 'assets', 'tests']

#----------------------------------------------------------
# RequestHandler
#----------------------------------------------------------
# Thread local global request object
_request_stack = werkzeug.local.LocalStack()
request = _request_stack()
"""
    A global proxy that always redirect to the current request object.
"""

def replace_request_password(args):
    # password is always 3rd argument in a request, we replace it in RPC logs
    # so it's easier to forward logs for diagnostics/debugging purposes...
    if len(args) > 2:
        args = list(args)
        args[2] = '*'
    return tuple(args)


# don't trigger debugger for those exceptions, they carry user-facing warnings
# and indications, they're not necessarily indicative of anything being
# *broken*
NO_POSTMORTEM = (odoo.exceptions.AccessDenied,
                 odoo.exceptions.UserError,
                 odoo.exceptions.RedirectWarning)


def dispatch_rpc(service_name, method, params):
    """ Handle a RPC call.

    This is pure Python code, the actual marshalling (from/to XML-RPC) is done
    in a upper layer.
    """
    try:
        rpc_request_flag = rpc_request.isEnabledFor(logging.DEBUG)
        rpc_response_flag = rpc_response.isEnabledFor(logging.DEBUG)
        if rpc_request_flag or rpc_response_flag:
            start_time = time.time()
            start_memory = 0
            if psutil:
                start_memory = memory_info(psutil.Process(os.getpid()))
            if rpc_request and rpc_response_flag:
                odoo.netsvc.log(rpc_request, logging.DEBUG, '%s.%s' % (service_name, method), replace_request_password(params))

        threading.current_thread().uid = None
        threading.current_thread().dbname = None
        if service_name == 'common':
            dispatch = odoo.service.common.dispatch
        elif service_name == 'db':
            dispatch = odoo.service.db.dispatch
        elif service_name == 'object':
            dispatch = odoo.service.model.dispatch
        result = dispatch(method, params)

        if rpc_request_flag or rpc_response_flag:
            end_time = time.time()
            end_memory = 0
            if psutil:
                end_memory = memory_info(psutil.Process(os.getpid()))
            logline = '%s.%s time:%.3fs mem: %sk -> %sk (diff: %sk)' % (service_name, method, end_time - start_time, start_memory / 1024, end_memory / 1024, (end_memory - start_memory)/1024)
            if rpc_response_flag:
                odoo.netsvc.log(rpc_response, logging.DEBUG, logline, result)
            else:
                odoo.netsvc.log(rpc_request, logging.DEBUG, logline, replace_request_password(params), depth=1)

        return result
    except NO_POSTMORTEM:
        raise
    except Exception as e:
        _logger.exception(odoo.tools.exception_to_unicode(e))
        odoo.tools.debugger.post_mortem(odoo.tools.config, sys.exc_info())
        raise


class WebRequest(object):
    """ Parent class for all Odoo Web request types, mostly deals with
    initialization and setup of the request object (the dispatching itself has
    to be handled by the subclasses)

    :param httprequest: a wrapped werkzeug Request object
    :type httprequest: :class:`werkzeug.wrappers.BaseRequest`

    .. attribute:: httprequest

        the original :class:`werkzeug.wrappers.Request` object provided to the
        request

    .. attribute:: params

        :class:`~collections.abc.Mapping` of request parameters, not generally
        useful as they're provided directly to the handler method as keyword
        arguments
    """
    def __init__(self, httprequest):
        self.httprequest = httprequest
        self.httpresponse = None
        self.endpoint = None
        self.endpoint_arguments = None
        self.auth_method = None
        self._db = self.session.db
        self._cr = None
        self._uid = None
        self._context = None
        self._env = None

        # prevents transaction commit, use when you catch an exception during handling
        self._failed = None

        # set db/uid trackers - they're cleaned up at the WSGI
        # dispatching phase in odoo.service.wsgi_server.application
        if self.db:
            threading.current_thread().dbname = self.db
        if self.session.uid:
            threading.current_thread().uid = self.session.uid

    @property
    def cr(self):
        """ :class:`~odoo.sql_db.Cursor` initialized for the current method call.

        Accessing the cursor when the current request uses the ``none``
        authentication will raise an exception.
        """
        # can not be a lazy_property because manual rollback in _call_function
        # if already set (?)
        if not self.db:
            raise RuntimeError('request not bound to a database')
        if not self._cr:
            self._cr = self.registry.cursor()
        return self._cr

    @property
    def uid(self):
        return self._uid

    @uid.setter
    def uid(self, val):
        self._uid = val
        self._env = None

    @property
    def context(self):
        """ :class:`~collections.abc.Mapping` of context values for the current request """
        if self._context is None:
            self._context = frozendict(self.session.context)
        return self._context

    @context.setter
    def context(self, val):
        self._context = frozendict(val)
        self._env = None

    @property
    def env(self):
        """ The :class:`~odoo.api.Environment` bound to current request. """
        if self._env is None:
            self._env = odoo.api.Environment(self.cr, self.uid, self.context)
        return self._env

    @lazy_property
    def session(self):
        """ :class:`OpenERPSession` holding the HTTP session data for the
        current http session
        """
        return self.httprequest.session

    def __enter__(self):
        _request_stack.push(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        _request_stack.pop()

        if self._cr:
            try:
                if exc_type is None and not self._failed:
                    self._cr.commit()
                    if self.registry:
                        self.registry.signal_changes()
                elif self.registry:
                    self.registry.reset_changes()
            finally:
                self._cr.close()
        # just to be sure no one tries to re-use the request
        self._db = None
        self.uid = None

    def set_handler(self, endpoint, arguments, auth):
        # is this needed ?
        arguments ={k: v for k, v in arguments.items()
                         if not k.startswith("_ignored_")}
        self.endpoint_arguments = arguments
        self.endpoint = endpoint
        self.auth_method = auth

    def _handle_exception(self, exception):
        """Called within an except block to allow converting exceptions
           to abitrary responses. Anything returned (except None) will
           be used as response."""
        self._failed = exception  # prevent tx commit
        if not isinstance(exception, NO_POSTMORTEM) \
                and not isinstance(exception, werkzeug.exceptions.HTTPException):
            odoo.tools.debugger.post_mortem(
                odoo.tools.config, sys.exc_info())

        # WARNING: do not inline or it breaks: raise...from evaluates strictly
        # LTR so would first remove traceback then copy lack of traceback
        new_cause = Exception().with_traceback(exception.__traceback__)
        new_cause.__cause__ = exception.__cause__ or exception.__context__
        # tries to provide good chained tracebacks, just re-raising exception
        # generates a weird message as stacks just get concatenated, exceptions
        # not guaranteed to copy.copy cleanly & we want `exception` as leaf (for
        # callers to check & look at)
        raise exception.with_traceback(None) from new_cause

    def redirect(self, location, code=303, local=True):
        # compatibility, Werkzeug support URL as location
        if isinstance(location, urls.URL):
            location = location.to_url()
        if local:
            location = '/' + urls.url_parse(location).replace(scheme='', netloc='').to_url().lstrip('/')
        if request and request.db:
            return request.registry['ir.http']._redirect(location, code)
        return werkzeug.utils.redirect(location, code, Response=Response)

    def redirect_query(self, location, query=None, code=303, local=True):
        if query:
            location += '?' + urls.url_encode(query)
        return self.redirect(location, code=code, local=local)

    def _is_cors_preflight(self, endpoint):
        return False

    def _call_function(self, *args, **kwargs):
        request = self
        if self.endpoint.routing['type'] != self._request_type:
            msg = "%s, %s: Function declared as capable of handling request of type '%s' but called with a request of type '%s'"
            params = (self.endpoint.original, self.httprequest.path, self.endpoint.routing['type'], self._request_type)
            _logger.info(msg, *params)
            raise werkzeug.exceptions.BadRequest(msg % params)

        if self.endpoint_arguments:
            kwargs.update(self.endpoint_arguments)

        # Backward for 7.0
        if self.endpoint.first_arg_is_req:
            args = (request,) + args

        first_time = True

        # Correct exception handling and concurrency retry
        @service_model.check
        def checked_call(___dbname, *a, **kw):
            nonlocal first_time
            # The decorator can call us more than once if there is an database error. In this
            # case, the request cursor is unusable. Rollback transaction to create a new one.
            if self._cr and not first_time:
                self._cr.rollback()
                self.env.clear()

            # Rewind files in case of failure
            if not first_time:
                for filename, file in self.httprequest.files.items():
                    if hasattr(file, "seekable") and file.seekable():
                        file.seek(0)
                    else:
                        raise RuntimeError("Cannot retry request on input file %r after serialization failure" % filename)

            first_time = False
            result = self.endpoint(*a, **kw)
            if isinstance(result, Response) and result.is_qweb:
                # Early rendering of lazy responses to benefit from @service_model.check protection
                result.flatten()
            if self._cr is not None:
                # flush here to avoid triggering a serialization error outside
                # of this context, which would not retry the call
                self._cr.flush()
            return result

        if self.db:
            return checked_call(self.db, *args, **kwargs)
        return self.endpoint(*args, **kwargs)

    @contextlib.contextmanager
    def registry_cr(self):
        warnings.warn('please use request.registry and request.cr directly', DeprecationWarning)
        yield (self.registry, self.cr)

    @property
    def registry(self):
        """
        The registry to the database linked to this request. Can be ``None``
        if the current request uses the ``none`` authentication.

        .. deprecated:: 8.0

            use :attr:`.env`
        """
        return odoo.registry(self.db)

    @property
    def db(self):
        """
        The database linked to this request. Can be ``None``
        if the current request uses the ``none`` authentication.
        """
        if not self._db:
            self._db = self.session.db
        return self._db

    def csrf_token(self, time_limit=None):
        """ Generates and returns a CSRF token for the current session

        :param time_limit: the CSRF token validity period (in seconds), or
                           ``None`` for the token to be valid as long as the
                           current user session is (the default)
        :type time_limit: int | None
        :returns: ASCII token string
        """
        token = self.session.sid

        # if no `time_limit` => distant 1y expiry (31536000) so max_ts acts as salt, e.g. vs BREACH
        max_ts = int(time.time() + (time_limit or 31536000))

        msg = '%s%s' % (token, max_ts)
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        assert secret, "CSRF protection requires a configured database secret"
        hm = hmac.new(secret.encode('ascii'), msg.encode('utf-8'), hashlib.sha1).hexdigest()
        return '%so%s' % (hm, max_ts)

    def validate_csrf(self, csrf):
        if not csrf:
            return False

        try:
            hm, _, max_ts = str(csrf).rpartition('o')
        except UnicodeEncodeError:
            return False

        if max_ts:
            try:
                if int(max_ts) < int(time.time()):
                    return False
            except ValueError:
                return False

        token = self.session.sid

        msg = '%s%s' % (token, max_ts)
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        assert secret, "CSRF protection requires a configured database secret"
        hm_expected = hmac.new(secret.encode('ascii'), msg.encode('utf-8'), hashlib.sha1).hexdigest()
        return consteq(hm, hm_expected)

def route(route=None, **kw):
    """Decorator marking the decorated method as being a handler for
    requests. The method must be part of a subclass of ``Controller``.

    :param route: string or array. The route part that will determine which
                  http requests will match the decorated method. Can be a
                  single string or an array of strings. See werkzeug's routing
                  documentation for the format of route expression (
                  http://werkzeug.pocoo.org/docs/routing/ ).
    :param type: The type of request, can be ``'http'`` or ``'json'``.
    :param auth: The type of authentication method, can on of the following:

                 * ``user``: The user must be authenticated and the current request
                   will perform using the rights of the user.
                 * ``public``: The user may or may not be authenticated. If she isn't,
                   the current request will perform using the shared Public user.
                 * ``none``: The method is always active, even if there is no
                   database. Mainly used by the framework and authentication
                   modules. There request code will not have any facilities to access
                   the database nor have any configuration indicating the current
                   database nor the current user.
    :param methods: A sequence of http methods this route applies to. If not
                    specified, all methods are allowed.
    :param cors: The Access-Control-Allow-Origin cors directive value.
    :param bool csrf: Whether CSRF protection should be enabled for the route.

                      Defaults to ``True``. See :ref:`CSRF Protection
                      <csrf>` for more.

    .. _csrf:

    .. admonition:: CSRF Protection
        :class: alert-warning

        .. versionadded:: 9.0

        Odoo implements token-based `CSRF protection
        <https://en.wikipedia.org/wiki/CSRF>`_.

        CSRF protection is enabled by default and applies to *UNSAFE*
        HTTP methods as defined by :rfc:`7231` (all methods other than
        ``GET``, ``HEAD``, ``TRACE`` and ``OPTIONS``).

        CSRF protection is implemented by checking requests using
        unsafe methods for a value called ``csrf_token`` as part of
        the request's form data. That value is removed from the form
        as part of the validation and does not have to be taken in
        account by your own form processing.

        When adding a new controller for an unsafe method (mostly POST
        for e.g. forms):

        * if the form is generated in Python, a csrf token is
          available via :meth:`request.csrf_token()
          <odoo.http.WebRequest.csrf_token`, the
          :data:`~odoo.http.request` object is available by default
          in QWeb (python) templates, it may have to be added
          explicitly if you are not using QWeb.

        * if the form is generated in Javascript, the CSRF token is
          added by default to the QWeb (js) rendering context as
          ``csrf_token`` and is otherwise available as ``csrf_token``
          on the ``web.core`` module:

          .. code-block:: javascript

              require('web.core').csrf_token

        * if the endpoint can be called by external parties (not from
          Odoo) as e.g. it is a REST API or a `webhook
          <https://en.wikipedia.org/wiki/Webhook>`_, CSRF protection
          must be disabled on the endpoint. If possible, you may want
          to implement other methods of request validation (to ensure
          it is not called by an unrelated third-party).

    """
    routing = kw.copy()
    assert 'type' not in routing or routing['type'] in ("http", "json")
    def decorator(f):
        if route:
            if isinstance(route, list):
                routes = route
            else:
                routes = [route]
            routing['routes'] = routes
            wrong = routing.pop('method', None)
            if wrong:
                kw.setdefault('methods', wrong)
                _logger.warning("<function %s.%s> defined with invalid routing parameter 'method', assuming 'methods'", f.__module__, f.__name__)

        @functools.wraps(f)
        def response_wrap(*args, **kw):
            # if controller cannot be called with extra args (utm, debug, ...), call endpoint ignoring them
            params = inspect.signature(f).parameters.values()
            is_kwargs = lambda p: p.kind == inspect.Parameter.VAR_KEYWORD
            if not any(is_kwargs(p) for p in params):  # missing **kw
                is_keyword_compatible = lambda p: p.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY)
                fargs = {p.name for p in params if is_keyword_compatible(p)}
                ignored = ['<%s=%s>' % (k, kw.pop(k)) for k in list(kw) if k not in fargs]
                if ignored:
                    _logger.info("<function %s.%s> called ignoring args %s" % (f.__module__, f.__name__, ', '.join(ignored)))

            response = f(*args, **kw)
            if isinstance(response, Response) or f.routing_type == 'json':
                return response

            if isinstance(response, (bytes, str)):
                return Response(response)

            if isinstance(response, werkzeug.exceptions.HTTPException):
                response = response.get_response(request.httprequest.environ)
            if isinstance(response, werkzeug.wrappers.Response):
                response = Response.force_type(response)
                response.set_default()
                return response

            _logger.warning("<function %s.%s> returns an invalid response type for an http request" % (f.__module__, f.__name__))
            return response
        response_wrap.routing = routing
        response_wrap.original_func = f
        return response_wrap
    return decorator

class JsonRequest(WebRequest):
    """ Request handler for `JSON-RPC 2
    <http://www.jsonrpc.org/specification>`_ over HTTP

    * ``method`` is ignored
    * ``params`` must be a JSON object (not an array) and is passed as keyword
      arguments to the handler method
    * the handler method's result is returned as JSON-RPC ``result`` and
      wrapped in the `JSON-RPC Response
      <http://www.jsonrpc.org/specification#response_object>`_

    Successful request::

      --> {"jsonrpc": "2.0",
           "method": "call",
           "params": {"context": {},
                      "arg1": "val1" },
           "id": null}

      <-- {"jsonrpc": "2.0",
           "result": { "res1": "val1" },
           "id": null}

    Request producing a error::

      --> {"jsonrpc": "2.0",
           "method": "call",
           "params": {"context": {},
                      "arg1": "val1" },
           "id": null}

      <-- {"jsonrpc": "2.0",
           "error": {"code": 1,
                     "message": "End user error message.",
                     "data": {"code": "codestring",
                              "debug": "traceback" } },
           "id": null}

    """
    _request_type = "json"

    def __init__(self, *args):
        super(JsonRequest, self).__init__(*args)

        self.params = {}

        args = self.httprequest.args
        request = None
        request_id = args.get('id')

        # regular jsonrpc2
        if not hasattr(self.httprequest._HTTPRequest__wrapped, 'charset'):
            # see https://github.com/pallets/werkzeug/pull/2768
            request = self.httprequest.get_data().decode('utf-8')
        else:
            request = self.httprequest.get_data().decode(self.httprequest.charset)

        # Read POST content or POST Form Data named "request"
        try:
            self.jsonrequest = json.loads(request)
        except ValueError:
            msg = 'Invalid JSON data: %r' % (request,)
            _logger.info('%s: %s', self.httprequest.path, msg)
            raise werkzeug.exceptions.BadRequest(msg)

        self.params = dict(self.jsonrequest.get("params", {}))
        self.context = self.params.pop('context', dict(self.session.context))

    def _json_response(self, result=None, error=None):
        response = {
            'jsonrpc': '2.0',
            'id': self.jsonrequest.get('id')
            }
        if error is not None:
            response['error'] = error
        if result is not None:
            response['result'] = result

        mime = 'application/json'
        body = json.dumps(response, default=date_utils.json_default)

        return Response(
            body, status=error and error.pop('http_status', 200) or 200,
            headers=[('Content-Type', mime), ('Content-Length', len(body))]
        )

    def _handle_exception(self, exception):
        """Called within an except block to allow converting exceptions
           to arbitrary responses. Anything returned (except None) will
           be used as response."""
        try:
            return super(JsonRequest, self)._handle_exception(exception)
        except Exception:
            if not isinstance(exception, SessionExpiredException):
                if exception.args and exception.args[0] == "bus.Bus not available in test mode":
                    _logger.info(exception)
                elif isinstance(exception, (odoo.exceptions.UserError,
                                            werkzeug.exceptions.NotFound)):
                    _logger.warning(exception)
                else:
                    _logger.exception("Exception during JSON request handling.")
            error = {
                'code': 200,
                'message': "Odoo Server Error",
                'data': serialize_exception(exception),
            }
            if isinstance(exception, werkzeug.exceptions.NotFound):
                error['http_status'] = 404
                error['code'] = 404
                error['message'] = "404: Not Found"
            if isinstance(exception, AuthenticationError):
                error['code'] = 100
                error['message'] = "Odoo Session Invalid"
            if isinstance(exception, SessionExpiredException):
                error['code'] = 100
                error['message'] = "Odoo Session Expired"
            return self._json_response(error=error)

    def dispatch(self):
        rpc_request_flag = rpc_request.isEnabledFor(logging.DEBUG)
        rpc_response_flag = rpc_response.isEnabledFor(logging.DEBUG)
        if rpc_request_flag or rpc_response_flag:
            endpoint = self.endpoint.method.__name__
            model = self.params.get('model')
            method = self.params.get('method')
            args = self.params.get('args', [])

            start_time = time.time()
            start_memory = 0
            if psutil:
                start_memory = memory_info(psutil.Process(os.getpid()))
            if rpc_request and rpc_response_flag:
                rpc_request.debug('%s: %s %s, %s',
                    endpoint, model, method, pprint.pformat(args))

        result = self._call_function(**self.params)

        if rpc_request_flag or rpc_response_flag:
            end_time = time.time()
            end_memory = 0
            if psutil:
                end_memory = memory_info(psutil.Process(os.getpid()))
            logline = '%s: %s %s: time:%.3fs mem: %sk -> %sk (diff: %sk)' % (
                endpoint, model, method, end_time - start_time, start_memory / 1024, end_memory / 1024, (end_memory - start_memory)/1024)
            if rpc_response_flag:
                rpc_response.debug('%s, %s', logline, pprint.pformat(result))
            else:
                rpc_request.debug(logline)

        return self._json_response(result)


def serialize_exception(e):
    return {
        "name": type(e).__module__ + "." + type(e).__name__ if type(e).__module__ else type(e).__name__,
        "debug": traceback.format_exc(),
        "message": ustr(e),
        "arguments": e.args,
        "context": getattr(e, 'context', {}),
    }


class HttpRequest(WebRequest):
    """ Handler for the ``http`` request type.

    matched routing parameters, query string parameters, form_ parameters
    and files are passed to the handler method as keyword arguments.

    In case of name conflict, routing parameters have priority.

    The handler method's result can be:

    * a falsy value, in which case the HTTP response will be an
      `HTTP 204`_ (No Content)
    * a werkzeug Response object, which is returned as-is
    * a ``str`` or ``unicode``, will be wrapped in a Response object and
      interpreted as HTML

    .. _form: http://www.w3.org/TR/html401/interact/forms.html#h-17.13.4.2
    .. _HTTP 204: http://tools.ietf.org/html/rfc7231#section-6.3.5
    """
    _request_type = "http"

    def __init__(self, *args):
        super(HttpRequest, self).__init__(*args)
        params = collections.OrderedDict(self.httprequest.args)
        params.update(self.httprequest.form)
        params.update(self.httprequest.files)
        params.pop('session_id', None)
        self.params = params

    def _handle_exception(self, exception):
        """Called within an except block to allow converting exceptions
           to abitrary responses. Anything returned (except None) will
           be used as response."""
        try:
            return super(HttpRequest, self)._handle_exception(exception)
        except SessionExpiredException:
            if not request.params.get('noredirect'):
                redirect = request.httprequest.url
                query = werkzeug.urls.url_encode({
                    'redirect': redirect,
                })
                return request.redirect('/web/login?%s' % query)
        except werkzeug.exceptions.HTTPException as e:
            return e

    def _is_cors_preflight(self, endpoint):
        return request.httprequest.method == 'OPTIONS' and endpoint and endpoint.routing.get('cors')

    def dispatch(self):
        if self._is_cors_preflight(request.endpoint):
            headers = {
                'Access-Control-Max-Age': 60 * 60 * 24,
                'Access-Control-Allow-Headers': 'Origin, X-Requested-With, Content-Type, Accept, Authorization'
            }
            return Response(status=200, headers=headers)

        if request.httprequest.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE') \
                and request.endpoint.routing.get('csrf', True): # csrf checked by default
            token = self.params.pop('csrf_token', None)
            if not self.validate_csrf(token):
                if token is not None:
                    _logger.warning("CSRF validation failed on path '%s'",
                                 request.httprequest.path)
                else:
                    _logger.warning("""No CSRF validation token provided for path '%s'

Odoo URLs are CSRF-protected by default (when accessed with unsafe
HTTP methods). See
https://www.odoo.com/documentation/15.0/developer/reference/addons/http.html#csrf for
more details.

* if this endpoint is accessed through Odoo via py-QWeb form, embed a CSRF
  token in the form, Tokens are available via `request.csrf_token()`
  can be provided through a hidden input and must be POST-ed named
  `csrf_token` e.g. in your form add:

      <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>

* if the form is generated or posted in javascript, the token value is
  available as `csrf_token` on `web.core` and as the `csrf_token`
  value in the default js-qweb execution context

* if the form is accessed by an external third party (e.g. REST API
  endpoint, payment gateway callback) you will need to disable CSRF
  protection (and implement your own protection if necessary) by
  passing the `csrf=False` parameter to the `route` decorator.
                    """, request.httprequest.path)

                raise werkzeug.exceptions.BadRequest('Session expired (invalid CSRF token)')

        r = self._call_function(**self.params)
        if not r:
            r = Response(status=204)  # no content
        return r

    def make_response(self, data, headers=None, cookies=None):
        """ Helper for non-HTML responses, or HTML responses with custom
        response headers or cookies.

        While handlers can just return the HTML markup of a page they want to
        send as a string if non-HTML data is returned they need to create a
        complete response object, or the returned data will not be correctly
        interpreted by the clients.

        :param basestring data: response body
        :param headers: HTTP headers to set on the response
        :type headers: ``[(name, value)]``
        :param collections.abc.Mapping cookies: cookies to set on the client
        """
        response = Response(data, headers=headers)
        if cookies:
            for k, v in cookies.items():
                response.set_cookie(k, v)
        return response

    def render(self, template, qcontext=None, lazy=True, **kw):
        """ Lazy render of a QWeb template.

        The actual rendering of the given template will occur at then end of
        the dispatching. Meanwhile, the template and/or qcontext can be
        altered or even replaced by a static response.

        :param basestring template: template to render
        :param dict qcontext: Rendering context to use
        :param bool lazy: whether the template rendering should be deferred
                          until the last possible moment
        :param kw: forwarded to werkzeug's Response object
        """
        response = Response(template=template, qcontext=qcontext, **kw)
        if not lazy:
            return response.render()
        return response

    def not_found(self, description=None):
        """ Shortcut for a `HTTP 404
        <http://tools.ietf.org/html/rfc7231#section-6.5.4>`_ (Not Found)
        response
        """
        return werkzeug.exceptions.NotFound(description)

#----------------------------------------------------------
# Controller and route registration
#----------------------------------------------------------
addons_manifest = {}
controllers_per_module = collections.defaultdict(list)

class ControllerType(type):
    def __init__(cls, name, bases, attrs):
        super(ControllerType, cls).__init__(name, bases, attrs)

        # flag old-style methods with req as first argument
        for k, v in attrs.items():
            if inspect.isfunction(v) and hasattr(v, 'original_func'):
                # Set routing type on original functions
                routing_type = v.routing.get('type')
                parent = [claz for claz in bases if isinstance(claz, ControllerType) and hasattr(claz, k)]
                parent_routing_type = getattr(parent[0], k).original_func.routing_type if parent else routing_type or 'http'
                if routing_type is not None and routing_type is not parent_routing_type:
                    routing_type = parent_routing_type
                    _logger.warning("Subclass re-defines <function %s.%s.%s> with different type than original."
                                    " Will use original type: %r" % (cls.__module__, cls.__name__, k, parent_routing_type))
                v.original_func.routing_type = routing_type or parent_routing_type

                sign = inspect.signature(v.original_func)
                first_arg = list(sign.parameters)[1] if len(sign.parameters) >= 2 else None
                if first_arg in ["req", "request"]:
                    v._first_arg_is_req = True

        # store the controller in the controllers list
        name_class = ("%s.%s" % (cls.__module__, cls.__name__), cls)
        class_path = name_class[0].split(".")
        if not class_path[:2] == ["odoo", "addons"]:
            module = ""
        else:
            # we want to know all modules that have controllers
            module = class_path[2]
        # but we only store controllers directly inheriting from Controller
        if not "Controller" in globals() or not Controller in bases:
            return
        controllers_per_module[module].append(name_class)

Controller = ControllerType('Controller', (object,), {})

class EndPoint(object):
    def __init__(self, method, routing):
        self.method = method
        self.original = getattr(method, 'original_func', method)
        self.routing = frozendict(routing)
        self.arguments = {}

    @property
    def first_arg_is_req(self):
        # Backward for 7.0
        return getattr(self.method, '_first_arg_is_req', False)

    def __call__(self, *args, **kw):
        return self.method(*args, **kw)

    # werkzeug will use these EndPoint objects as keys of a dictionary
    # (the RoutingMap._rules_by_endpoint mapping).
    # When Odoo clears the routing map, new EndPoint objects are created,
    # most of them with the same values.
    # The __eq__ and __hash__ magic methods allow older EndPoint objects
    # to be still valid keys of the RoutingMap.
    # For example, website._get_canonical_url_localized may use
    # such an old endpoint if the routing map was cleared.
    def __eq__(self, other):
        try:
            return self._as_tuple() == other._as_tuple()
        except AttributeError:
            return False

    def __hash__(self):
        return hash(self._as_tuple())

    def _as_tuple(self):
        return (self.original, self.routing)

    def __repr__(self):
        return '<EndPoint method=%r routing=%r>' % (self.method, self.routing)


def _generate_routing_rules(modules, nodb_only, converters=None):
    def get_subclasses(klass):
        def valid(c):
            return c.__module__.startswith('odoo.addons.') and c.__module__.split(".")[2] in modules
        subclasses = klass.__subclasses__()
        result = []
        for subclass in subclasses:
            if valid(subclass):
                result.extend(get_subclasses(subclass))
        if not result and valid(klass):
            result = [klass]
        return result

    for module in modules:
        if module not in controllers_per_module:
            continue

        for _, cls in controllers_per_module[module]:
            subclasses = list(unique(c for c in get_subclasses(cls) if c is not cls))
            if subclasses:
                name = "%s (extended by %s)" % (cls.__name__, ', '.join(sub.__name__ for sub in subclasses))
                cls = type(name, tuple(reversed(subclasses)), {})

            o = cls()
            members = inspect.getmembers(o, inspect.ismethod)
            for _, mv in members:
                if hasattr(mv, 'routing'):
                    routing = dict(type='http', auth='user', methods=None, routes=None)
                    methods_done = list()
                    # update routing attributes from subclasses(auth, methods...)
                    for claz in reversed(mv.__self__.__class__.mro()):
                        fn = getattr(claz, mv.__name__, None)
                        if fn and hasattr(fn, 'routing') and fn not in methods_done:
                            methods_done.append(fn)
                            routing.update(fn.routing)
                    if not nodb_only or routing['auth'] == "none":
                        assert routing['routes'], "Method %r has not route defined" % mv
                        endpoint = EndPoint(mv, routing)
                        for url in routing['routes']:
                            yield (url, endpoint, routing)


#----------------------------------------------------------
# HTTP Sessions
#----------------------------------------------------------
class AuthenticationError(Exception):
    pass

class SessionExpiredException(Exception):
    pass

class OpenERPSession(sessions.Session):
    def __init__(self, *args, **kwargs):
        self.inited = False
        self.modified = False
        self.rotate = False
        super(OpenERPSession, self).__init__(*args, **kwargs)
        self.inited = True
        self._default_values()
        self.modified = False

    def __getattr__(self, attr):
        return self.get(attr, None)
    def __setattr__(self, k, v):
        if getattr(self, "inited", False):
            try:
                object.__getattribute__(self, k)
            except:
                return self.__setitem__(k, v)
        object.__setattr__(self, k, v)

    def authenticate(self, db, login=None, password=None):
        """
        Authenticate the current user with the given db, login and
        password. If successful, store the authentication parameters in the
        current session and request, unless multi-factor-authentication
        is activated. In that case, that last part will be done by
        :ref:`finalize`.
        """

        wsgienv = request.httprequest.environ
        env = dict(
            interactive=True,
            base_location=request.httprequest.url_root.rstrip('/'),
            HTTP_HOST=wsgienv['HTTP_HOST'],
            REMOTE_ADDR=wsgienv['REMOTE_ADDR'],
        )
        uid = odoo.registry(db)['res.users'].authenticate(db, login, password, env)
        self.pre_uid = uid

        self.rotate = True
        self.db = db
        self.login = login

        user = request.env(user=uid)['res.users'].browse(uid)
        if not user._mfa_url():
            self.finalize()

        return uid

    def finalize(self):
        """ Finalizes a partial session, should be called on MFA validation to
        convert a partial / pre-session into a full-fledged "logged-in" one
        """
        self.rotate = True
        request.uid = self.uid = self.pop('pre_uid')
        user = request.env(user=self.uid)['res.users'].browse(self.uid)
        self.session_token = user._compute_session_token(self.sid)
        self.get_context()

    def check_security(self):
        """
        Check the current authentication parameters to know if those are still
        valid. This method should be called at each request. If the
        authentication fails, a :exc:`SessionExpiredException` is raised.
        """
        if not self.db or not self.uid:
            raise SessionExpiredException("Session expired")
        # We create our own environment instead of the request's one.
        # to avoid creating it without the uid since request.uid isn't set yet
        env = odoo.api.Environment(request.cr, self.uid, self.context)
        # here we check if the session is still valid
        if not security.check_session(self, env):
            raise SessionExpiredException("Session expired")

    def logout(self, keep_db=False):
        for k in list(self):
            if not (keep_db and k == 'db') and k != 'debug':
                del self[k]
        self._default_values()
        self.rotate = True

    def _default_values(self):
        self.setdefault("db", None)
        self.setdefault("uid", None)
        self.setdefault("login", None)
        self.setdefault("session_token", None)
        self.setdefault("context", {})
        self.setdefault("debug", '')

    def get_context(self):
        """
        Re-initializes the current user's session context (based on his
        preferences) by calling res.users.get_context() with the old context.

        :returns: the new context
        """
        assert self.uid, "The user needs to be logged-in to initialize his context"
        self.context = dict(request.env['res.users'].context_get() or {})
        self.context['uid'] = self.uid
        self._fix_lang(self.context)
        return self.context

    def _fix_lang(self, context):
        """ OpenERP provides languages which may not make sense and/or may not
        be understood by the web client's libraries.

        Fix those here.

        :param dict context: context to fix
        """
        lang = context.get('lang')

        # inane OpenERP locale
        if lang == 'ar_AR':
            lang = 'ar'

        # lang to lang_REGION (datejs only handles lang_REGION, no bare langs)
        if lang in babel.core.LOCALE_ALIASES:
            lang = babel.core.LOCALE_ALIASES[lang]

        context['lang'] = lang or 'en_US'

    def save_action(self, action):
        """
        This method store an action object in the session and returns an integer
        identifying that action. The method get_action() can be used to get
        back the action.

        :param the_action: The action to save in the session.
        :type the_action: anything
        :return: A key identifying the saved action.
        :rtype: integer
        """
        saved_actions = self.setdefault('saved_actions', {"next": 1, "actions": {}})
        # we don't allow more than 10 stored actions
        if len(saved_actions["actions"]) >= 10:
            del saved_actions["actions"][min(saved_actions["actions"])]
        key = saved_actions["next"]
        saved_actions["actions"][key] = action
        saved_actions["next"] = key + 1
        self.modified = True
        return key

    def get_action(self, key):
        """
        Gets back a previously saved action. This method can return None if the action
        was saved since too much time (this case should be handled in a smart way).

        :param key: The key given by save_action()
        :type key: integer
        :return: The saved action or None.
        :rtype: anything
        """
        saved_actions = self.get('saved_actions', {})
        return saved_actions.get("actions", {}).get(key)

def session_gc(session_store):
    if random.random() < 0.001:
        # we keep session one week
        last_week = time.time() - 60*60*24*7
        for fname in os.listdir(session_store.path):
            path = os.path.join(session_store.path, fname)
            try:
                if os.path.getmtime(path) < last_week:
                    os.unlink(path)
            except OSError:
                pass

ODOO_DISABLE_SESSION_GC = str2bool(os.environ.get('ODOO_DISABLE_SESSION_GC', '0'))

if ODOO_DISABLE_SESSION_GC:
    # empty function, in case another module would be
    # calling it out of setup_session()
    session_gc = lambda s: None


#----------------------------------------------------------
# WSGI Layer
#----------------------------------------------------------
# Add potentially missing (older ubuntu) font mime types
mimetypes.add_type('application/font-woff', '.woff')
mimetypes.add_type('application/vnd.ms-fontobject', '.eot')
mimetypes.add_type('application/x-font-ttf', '.ttf')
# Add potentially missing (detected on windows) svg mime types
mimetypes.add_type('image/svg+xml', '.svg')
# this one can be present on windows with the value 'text/plain' which breaks
# loading js files from an addon's static folder
mimetypes.add_type('text/javascript', '.js')


def make_request_wrap_methods(attr):
    def getter(self):
        return getattr(self._HTTPRequest__wrapped, attr)

    def setter(self, value):
        return setattr(self._HTTPRequest__wrapped, attr, value)

    return getter, setter


class HTTPRequest:
    def __init__(self, environ):
        httprequest = werkzeug.wrappers.Request(environ)
        httprequest.user_agent_class = UserAgent  # use vendored userAgent since it will be removed in 2.1
        httprequest.parameter_storage_class = werkzeug.datastructures.ImmutableOrderedMultiDict

        self.__wrapped = httprequest
        self.__environ = self.__wrapped.environ
        self.environ = {
            key: value
            for key, value in self.__environ.items()
            if not key.startswith(('werkzeug.', 'wsgi.')) or key in ['wsgi.url_scheme', 'werkzeug.proxy_fix.orig']
        }

    def __enter__(self):
        return self


HTTPREQUEST_ATTRIBUTES = [
    '__str__', '__repr__', '__exit__',
    'accept_charsets', 'accept_languages', 'accept_mimetypes', 'access_route', 'args', 'authorization', 'base_url',
    'charset', 'content_encoding', 'content_length', 'content_md5', 'content_type', 'cookies', 'data', 'date',
    'encoding_errors', 'files', 'form', 'full_path', 'get_data', 'get_json', 'headers', 'host', 'host_url', 'if_match',
    'if_modified_since', 'if_none_match', 'if_range', 'if_unmodified_since', 'is_json', 'is_secure', 'json', 'method',
    'mimetype', 'mimetype_params', 'origin', 'path', 'pragma', 'query_string', 'range', 'referrer', 'remote_addr',
    'remote_user', 'root_path', 'root_url', 'scheme', 'script_root', 'server', 'session', 'trusted_hosts', 'url',
    'url_charset', 'url_root', 'user_agent', 'values',
]
for attr in HTTPREQUEST_ATTRIBUTES:
    setattr(HTTPRequest, attr, property(*make_request_wrap_methods(attr)))


class Response(werkzeug.wrappers.Response):
    """ Response object passed through controller route chain.

    In addition to the :class:`werkzeug.wrappers.Response` parameters, this
    class's constructor can take the following additional parameters
    for QWeb Lazy Rendering.

    :param basestring template: template to render
    :param dict qcontext: Rendering context to use
    :param int uid: User id to use for the ir.ui.view render call,
                    ``None`` to use the request's user (the default)

    these attributes are available as parameters on the Response object and
    can be altered at any time before rendering

    Also exposes all the attributes and methods of
    :class:`werkzeug.wrappers.Response`.
    """
    default_mimetype = 'text/html'
    def __init__(self, *args, **kw):
        template = kw.pop('template', None)
        qcontext = kw.pop('qcontext', None)
        uid = kw.pop('uid', None)
        super(Response, self).__init__(*args, **kw)
        self.set_default(template, qcontext, uid)

    def set_default(self, template=None, qcontext=None, uid=None):
        self.template = template
        self.qcontext = qcontext or dict()
        self.qcontext['response_template'] = self.template
        self.uid = uid
        # Support for Cross-Origin Resource Sharing
        if request.endpoint and 'cors' in request.endpoint.routing:
            self.headers.set('Access-Control-Allow-Origin', request.endpoint.routing['cors'])
            methods = 'GET, POST'
            if request.endpoint.routing['type'] == 'json':
                methods = 'POST'
            elif request.endpoint.routing.get('methods'):
                methods = ', '.join(request.endpoint.routing['methods'])
            self.headers.set('Access-Control-Allow-Methods', methods)

    @property
    def is_qweb(self):
        return self.template is not None

    def render(self):
        """ Renders the Response's template, returns the result
        """
        env = request.env(user=self.uid or request.uid or odoo.SUPERUSER_ID)
        self.qcontext['request'] = request
        return env["ir.ui.view"]._render_template(self.template, self.qcontext)

    def flatten(self):
        """ Forces the rendering of the response's template, sets the result
        as response body and unsets :attr:`.template`
        """
        if self.template:
            self.response.append(self.render())
            self.template = None

class DisableCacheMiddleware(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def start_wrapped(status, headers):
            req = HTTPRequest(environ)
            root.setup_session(req)
            if req.session and req.session.debug and not 'wkhtmltopdf' in req.headers.get('User-Agent'):

                if "assets" in req.session.debug and (".js" in req.base_url or ".css" in req.base_url):
                    new_cache_control = 'no-store'
                else:
                    new_cache_control = 'no-cache'

                cache_control_value = new_cache_control
                new_headers = []
                for k, v in headers:
                    if k.lower() != 'cache-control':
                        new_headers.append((k, v))
                    elif new_cache_control not in v:
                        cache_control_value += ', %s' % v

                new_headers.append(('Cache-Control', cache_control_value))
                start_response(status, new_headers)
            else:
                start_response(status, headers)
        return self.app(environ, start_wrapped)

class Root(object):
    """Root WSGI application for the OpenERP Web Client.
    """
    def __init__(self):
        self._loaded = False

    @lazy_property
    def session_store(self):
        # Setup http sessions
        path = odoo.tools.config.session_dir
        _logger.debug('HTTP sessions stored in: %s', path)
        if ODOO_DISABLE_SESSION_GC:
            _logger.info('Default session GC disabled, manual GC required.')
        return sessions.FilesystemSessionStore(
            path, session_class=OpenERPSession, renew_missing=True)

    @lazy_property
    def nodb_routing_map(self):
        _logger.info("Generating nondb routing")
        routing_map = werkzeug.routing.Map(strict_slashes=False, converters=None)
        for url, endpoint, routing in odoo.http._generate_routing_rules([''] + odoo.conf.server_wide_modules, True):
            rule = werkzeug.routing.Rule(url, endpoint=endpoint, methods=routing['methods'])
            rule.merge_slashes = False
            routing_map.add(rule)
        return routing_map

    def __call__(self, environ, start_response):
        """ Handle a WSGI request
        """
        if not self._loaded:
            self._loaded = True
            self.load_addons()
        return self.dispatch(environ, start_response)

    def load_addons(self):
        """ Load all addons from addons path containing static files and
        controllers and configure them.  """
        # TODO should we move this to ir.http so that only configured modules are served ?
        statics = {}
        manifests = addons_manifest
        for addons_path in odoo.addons.__path__:
            for module in sorted(os.listdir(str(addons_path))):
                if module not in manifests:
                    # Deal with the manifest first
                    mod_path = opj(addons_path, module)
                    manifest = read_manifest(addons_path, module)
                    if not manifest or (not manifest.get('installable', True) and 'assets' not in manifest):
                        continue
                    manifest['addons_path'] = addons_path
                    manifests[module] = manifest
                    # Then deal with the statics
                    path_static = opj(addons_path, module, 'static')
                    if os.path.isdir(path_static):
                        _logger.debug("Loading %s", module)
                        statics['/%s/static' % module] = path_static

        if statics:
            _logger.info("HTTP Configuring static files")
        app = SharedDataMiddleware(self.dispatch, statics, cache_timeout=STATIC_CACHE)
        self.dispatch = DisableCacheMiddleware(app)

    def setup_session(self, httprequest):
        # recover or create session
        session_gc(self.session_store)

        sid = httprequest.args.get('session_id')
        explicit_session = True
        if not sid:
            sid =  httprequest.headers.get("X-Openerp-Session-Id")
        if not sid:
            sid = httprequest.cookies.get('session_id')
            explicit_session = False
        if sid is None:
            httprequest.session = self.session_store.new()
        else:
            httprequest.session = self.session_store.get(sid)
        return explicit_session

    def setup_db(self, httprequest):
        db = httprequest.session.db
        # Check if session.db is legit
        if db:
            if db not in db_filter([db], httprequest=httprequest):
                _logger.warning("Logged into database '%s', but dbfilter "
                             "rejects it; logging session out.", db)
                httprequest.session.logout()
                db = None

        if not db:
            httprequest.session.db = db_monodb(httprequest)

    def setup_lang(self, httprequest):
        if "lang" not in httprequest.session.context:
            alang = httprequest.accept_languages.best or "en-US"
            try:
                code, territory, _, _ = babel.core.parse_locale(alang, sep='-')
                if territory:
                    lang = '%s_%s' % (code, territory)
                else:
                    lang = babel.core.LOCALE_ALIASES[code]
            except (ValueError, KeyError):
                lang = 'en_US'
            httprequest.session.context["lang"] = lang

    def get_request(self, httprequest):
        # deduce type of request
        if httprequest.mimetype in ("application/json", "application/json-rpc"):
            return JsonRequest(httprequest)
        else:
            return HttpRequest(httprequest)

    def get_response(self, httprequest, result, explicit_session):
        if isinstance(result, Response) and result.is_qweb:
            try:
                result.flatten()
            except Exception as e:
                if request.db:
                    result = request.registry['ir.http']._handle_exception(e)
                else:
                    raise

        if isinstance(result, (bytes, str)):
            response = Response(result, mimetype='text/html')
        else:
            response = result
            self.set_csp(response)

        save_session = (not request.endpoint) or request.endpoint.routing.get('save_session', True)
        if not save_session:
            return response

        if httprequest.session.should_save:
            if httprequest.session.rotate:
                self.session_store.delete(httprequest.session)
                httprequest.session.sid = self.session_store.generate_key()
                if httprequest.session.uid:
                    httprequest.session.session_token = security.compute_session_token(httprequest.session, request.env)
                httprequest.session.modified = True
            self.session_store.save(httprequest.session)
        # We must not set the cookie if the session id was specified using a http header or a GET parameter.
        # There are two reasons to this:
        # - When using one of those two means we consider that we are overriding the cookie, which means creating a new
        #   session on top of an already existing session and we don't want to create a mess with the 'normal' session
        #   (the one using the cookie). That is a special feature of the Session Javascript class.
        # - It could allow session fixation attacks.
        if not explicit_session and hasattr(response, 'set_cookie'):
            response.set_cookie(
                'session_id', httprequest.session.sid, max_age=90 * 24 * 60 * 60, httponly=True)

        return response


    def set_csp(self, response):
        # ignore HTTP errors
        if not isinstance(response, werkzeug.wrappers.Response):
            return

        headers = response.headers
        if 'Content-Security-Policy' in headers:
            return

        mime, _params = cgi.parse_header(headers.get('Content-Type', ''))
        if not mime.startswith('image/'):
            return

        headers['Content-Security-Policy'] = "default-src 'none'"


    def dispatch(self, environ, start_response):
        """
        Performs the actual WSGI dispatching for the application.
        """
        try:
            httprequest = HTTPRequest(environ)

            current_thread = threading.current_thread()
            current_thread.url = httprequest.url
            current_thread.query_count = 0
            current_thread.query_time = 0
            current_thread.perf_t0 = time.time()

            explicit_session = self.setup_session(httprequest)
            self.setup_db(httprequest)
            self.setup_lang(httprequest)

            request = self.get_request(httprequest)

            def _dispatch_nodb():
                try:
                    func, arguments = self.nodb_routing_map.bind_to_environ(request.httprequest.environ).match()
                except werkzeug.exceptions.HTTPException as e:
                    return request._handle_exception(e)
                request.set_handler(func, arguments, "none")
                try:
                    result = request.dispatch()
                except Exception as e:
                    return request._handle_exception(e)
                return result

            request_manager = request
            if request.session.profile_session:
                request_manager = self.get_profiler_context_manager(request)

            with request_manager:
                db = request.session.db
                if db:
                    try:
                        odoo.registry(db).check_signaling()
                        with odoo.tools.mute_logger('odoo.sql_db'):
                            ir_http = request.registry['ir.http']
                    except (AttributeError, psycopg2.OperationalError, psycopg2.ProgrammingError):
                        # psycopg2 error or attribute error while constructing
                        # the registry. That means either
                        # - the database probably does not exists anymore
                        # - the database is corrupted
                        # - the database version doesn't match the server version
                        # Log the user out and fall back to nodb
                        request.session.logout()
                        if request.httprequest.path == '/web':
                            # Internal Server Error
                            raise
                        else:
                            # If requesting /web this will loop
                            result = _dispatch_nodb()
                    else:
                        result = ir_http._dispatch()
                else:
                    result = _dispatch_nodb()

                response = self.get_response(httprequest, result, explicit_session)
            return response(environ, start_response)

        except werkzeug.exceptions.HTTPException as e:
            return e(environ, start_response)

    def get_profiler_context_manager(self, request):
        """ Return a context manager that combines a profiler and ``request``. """
        if request.session.profile_session and request.session.db:
            if request.session.profile_expiration < str(datetime.now()):
                # avoid having session profiling for too long if user forgets to disable profiling
                request.session.profile_session = None
                _logger.warning("Profiling expiration reached, disabling profiling")
            elif 'set_profiling' in request.httprequest.path:
                _logger.debug("Profiling disabled on set_profiling route")
            elif request.httprequest.path.startswith('/longpolling'):
                _logger.debug("Profiling disabled for longpolling")
            elif odoo.evented:
                # only longpolling should be in a evented server, but this is an additional safety
                _logger.debug("Profiling disabled for evented server")
            else:
                try:
                    prof = profiler.Profiler(
                        db=request.session.db,
                        description=request.httprequest.full_path,
                        profile_session=request.session.profile_session,
                        collectors=request.session.profile_collectors,
                        params=request.session.profile_params,
                    )
                    return profiler.Nested(prof, request)
                except Exception:
                    _logger.exception("Failure during Profiler creation")
                    request.session.profile_session = None
        return request

    def get_db_router(self, db):
        if not db:
            return self.nodb_routing_map
        return request.registry['ir.http'].routing_map()

def db_list(force=False, httprequest=None):
    try:
        dbs = odoo.service.db.list_dbs(force)
    except psycopg2.OperationalError:
        return []
    return db_filter(dbs, httprequest=httprequest)

def db_filter(dbs, httprequest=None):
    httprequest = httprequest or request.httprequest
    h = httprequest.environ.get('HTTP_HOST', '').split(':')[0]
    d, _, r = h.partition('.')
    if d == "www" and r:
        d = r.partition('.')[0]
    if odoo.tools.config['dbfilter']:
        d, h = re.escape(d), re.escape(h)
        r = odoo.tools.config['dbfilter'].replace('%h', h).replace('%d', d)
        dbs = [i for i in dbs if re.match(r, i)]
    elif odoo.tools.config['db_name']:
        # In case --db-filter is not provided and --database is passed, Odoo will
        # use the value of --database as a comma separated list of exposed databases.
        exposed_dbs = set(db.strip() for db in odoo.tools.config['db_name'].split(','))
        dbs = sorted(exposed_dbs.intersection(dbs))
    return dbs

def db_monodb(httprequest=None):
    """
        Magic function to find the current database.

        Implementation details:

        * Magic
        * More magic

        Returns ``None`` if the magic is not magic enough.
    """
    httprequest = httprequest or request.httprequest

    dbs = db_list(True, httprequest)

    # try the db already in the session
    db_session = httprequest.session.db
    if db_session in dbs:
        return db_session

    # if there is only one possible db, we take that one
    if len(dbs) == 1:
        return dbs[0]
    return None

def send_file(filepath_or_fp, mimetype=None, as_attachment=False, filename=None, mtime=None,
              add_etags=True, cache_timeout=STATIC_CACHE, conditional=True):
    """This is a modified version of Flask's send_file()

    Sends the contents of a file to the client. This will use the
    most efficient method available and configured.  By default it will
    try to use the WSGI server's file_wrapper support.

    By default it will try to guess the mimetype for you, but you can
    also explicitly provide one.  For extra security you probably want
    to send certain files as attachment (HTML for instance).  The mimetype
    guessing requires a `filename` or an `attachment_filename` to be
    provided.

    Please never pass filenames to this function from user sources without
    checking them first.

    :param filepath_or_fp: the filename of the file to send.
                           Alternatively a file object might be provided
                           in which case `X-Sendfile` might not work and
                           fall back to the traditional method.  Make sure
                           that the file pointer is positioned at the start
                           of data to send before calling :func:`send_file`.
    :param mimetype: the mimetype of the file if provided, otherwise
                     auto detection happens.
    :param as_attachment: set to `True` if you want to send this file with
                          a ``Content-Disposition: attachment`` header.
    :param filename: the filename for the attachment if it differs from the file's filename or
                     if using file object without 'name' attribute (eg: E-tags with StringIO).
    :param mtime: last modification time to use for contitional response.
    :param add_etags: set to `False` to disable attaching of etags.
    :param conditional: set to `False` to disable conditional responses.

    :param cache_timeout: the timeout in seconds for the headers.
    """
    if isinstance(filepath_or_fp, str):
        if not filename:
            filename = os.path.basename(filepath_or_fp)
        file = open(filepath_or_fp, 'rb')
        if not mtime:
            mtime = os.path.getmtime(filepath_or_fp)
    else:
        file = filepath_or_fp
        if not filename:
            filename = getattr(file, 'name', None)

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if mimetype is None and filename:
        mimetype = mimetypes.guess_type(filename)[0]
    if mimetype is None:
        mimetype = 'application/octet-stream'

    headers = werkzeug.datastructures.Headers()
    if as_attachment:
        if filename is None:
            raise TypeError('filename unavailable, required for sending as attachment')
        headers.add('Content-Disposition', 'attachment', filename=filename)
        headers['Content-Length'] = size

    data = wrap_file(request.httprequest.environ, file)
    rv = Response(data, mimetype=mimetype, headers=headers,
                                    direct_passthrough=True)

    if isinstance(mtime, str):
        try:
            server_format = odoo.tools.misc.DEFAULT_SERVER_DATETIME_FORMAT
            mtime = datetime.strptime(mtime.split('.')[0], server_format)
        except Exception:
            mtime = None
    if mtime is not None:
        rv.last_modified = mtime

    rv.cache_control.public = True
    if cache_timeout:
        rv.cache_control.max_age = cache_timeout
        rv.expires = int(time.time() + cache_timeout)

    if add_etags and filename and mtime:
        rv.set_etag('odoo-%s-%s-%s' % (
            mtime,
            size,
            adler32(
                filename.encode('utf-8') if isinstance(filename, str)
                else filename
            ) & 0xffffffff
        ))
        if conditional:
            rv = rv.make_conditional(request.httprequest)
            # make sure we don't send x-sendfile for servers that
            # ignore the 304 status code for x-sendfile.
            if rv.status_code == 304:
                rv.headers.pop('x-sendfile', None)
    return rv

def content_disposition(filename):
    filename = odoo.tools.ustr(filename)
    escaped = urls.url_quote(filename, safe='', unsafe='()<>@,;:"/[]?={}\\*\'%')  # RFC6266

    return "attachment; filename*=UTF-8''%s" % escaped


def set_safe_image_headers(headers, content):
    """Return new headers based on `headers` but with `Content-Length` and
    `Content-Type` set appropriately depending on the given `content` only if it
    is safe to do, as well as `X-Content-Type-Options: nosniff` so that if the
    file is of an unsafe type, it is not interpreted as that type if the
    `Content-type` header was already set to a different mimetype
    """
    headers = werkzeug.datastructures.Headers(headers)
    safe_types = {'image/jpeg', 'image/png', 'image/gif', 'image/x-icon'}
    content_type = guess_mimetype(content)
    if content_type in safe_types:
        headers['Content-Type'] = content_type
    headers['X-Content-Type-Options'] = 'nosniff'
    headers['Content-Length'] = len(content)
    return list(headers)


#  main wsgi handler
root = Root()
