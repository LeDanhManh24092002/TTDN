# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import _monkeypatches
from . import _monkeypatches_pytz

from werkzeug import urls
if not hasattr(urls, 'url_join'):
    # see https://github.com/pallets/werkzeug/compare/2.3.0..3.0.0
    # see https://github.com/pallets/werkzeug/blob/2.3.0/src/werkzeug/urls.py for replacement
    from . import _monkeypatches_urls

from . import pycompat
from . import win32
from . import appdirs
from . import pdf
from . import cloc
from .config import config
from .misc import *
from .translate import *
from .image import *
from .sql import *
from .float_utils import *
from .mail import *
from .func import *
from .debugger import *
from .xml_utils import *
from .date_utils import *
from .convert import *
from .template_inheritance import *
from . import osutil
from .js_transpiler import transpile_javascript, is_odoo_module, URL_RE, ODOO_MODULE_RE
from .sourcemap_generator import SourceMapGenerator
