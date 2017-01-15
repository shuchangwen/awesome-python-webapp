#!/usr/bin/env python
#coding=utf-8

"""
这是一个简单的，轻量级的，WSGI兼容（Web Server GateWay Interface）的Web框架
WSGI概要：
    工作方式：WSGI server --->WSGI处理函数
    作用：将HTTP原始的请求、解析、响应这些交给WSGI server完成
          让我们专心用python编写Web业务，也就是WSGI处理函数
          所以WSGI是HTTP的一种高级封装

设计web框架的原因：
    1. WSGI提供的接口虽然比HTTP接口高级了不少，但和Web App的处理逻辑比，还是比较低级，
       我们需要在WSGI接口之上能进一步抽象，让我们专注于用一个函数处理一个URL，
       至于URL到函数的映射，就交给Web框架来做。
设计web框架接口：
    1. URL路由： 用于URL 到 处理函数的映射
    2. URL拦截： 用于根据URL做权限检测
    3. 视图： 用于HTML页面生成
    4. 数据模型： 用于抽取数据（见models模块）
    5. 事物数据：request数据和response数据的封装（thread local）
"""
import types, os, re, cgi, sys, time, datetime, functools, mimetypes, threading, logging, traceback, urllib
from db import Dict

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

######################################################
#实现事物数据接口，实现request数据和response数据的存储，
#是一个全局ThreadLocal对象
#######################################################
ctx = threading.local()

_RE_RESPONSE_STATUS = re.compile(r'^\d\d(\[\w\]+)?$')
_HEADER_X_POWERED_BY = ('X-Powered-By', 'transwarp/1.0')

# 用于时区转换
_TIMEDLTA_ZERO = datetime.timedelta(0)
_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')

#response status
_RE_RESPONSE_STATUS = {
    # Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',

    #Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

# Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}

_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',
)

_RESPONSE_HEADER_DICT = dict(zip(map(lambda  x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

class UTC(datetime.tzinfo):
    """
    tzinfo是一个基类，用于给datetime对象分配一个时区
    使用方式是把这个子类对象传递给datetime.tzinfo属性
    传递方法有2种：
        1.初始化的时候传入
        datetime(2000, 2, 17, 19, 10, 2, tzinfo=tz0)
        2.使用datetime对象的replace方法传入，从新生成一个datetime对象
        datetime.replace(tzinfo=tz0）
    """
    def __init__(self, utc):
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1) == '-'
            h = int(mt.group(2))
            m = int(mt.group(3))
            if minus:
                h, m = (-h), (-m)
                self._utcoffset = datetime.timedelta(hours=h, minutes=m)
                self._tzname = 'UTC%s' % utc
            else:
                raise ValueError('bad utc time zone')

    def utcoffset(self, dt):
        """
        表示与标准时区的偏移量
        :param dt:
        :return:
        """
        return self._utcoffset

    def dst(self, dt):
        """
        Daylight Saving Time夏令时
        :param dt:
        :return:
        """
        return _TIMEDLTA_ZERO

    def dzname(self, dt):
        """
        所在时区的名字
        :param dt:
        :return:
        """
        return self._tzname

    def __str__(self):
        return 'UTC timezone info object (%s)' % self._tzname

    __repr__ = __str__


#用于异常处理
class HttpError(Exception):
    """
    HttpError that defines http error code.
    """
    def __init__(self, code):
        """
        Init an HttpError with response code.
        :param code:
        """
        super(HttpError, self).__init__()
        self.status = '%d %s' % (code, _RE_RESPONSE_STATUS[code])

    def header(self, name, value):
        """
        添加header, 如果header 为空则添加powered by header
        :param name:
        :param value:
        :return:
        """
        if not self._headers:
            self._headers = [_HEADER_X_POWERED_BY]
        self._headers.append((name, value))

    @property
    def headers(self):
        """
        使用setter方法实现的header属性
        :return:
        """
        if hasattr(self, '_headers'):
            return self._headers
        return []
    def __str__(self):
        return self.status
    __repr__ = __str__

class RedirectError(HttpError):
    """
    RedirectError that defines http redirect code.
    """
    def __init__(self, code, location):
        """
        Init an HttpError with response code.
        :param code:
        :param location:
        """
        super(RedirectError, self).__init__(code)
        self.location = location

    def __str__(self):
        return '%s, %s' % (self.status, self.location)

    __repr__ = __str__


def badrequest():
    """
    Send a bad request response.
    """
    return HttpError(400)

def unauthorized():
    '''
    Send an unauthorized response.
    :return:
    '''
    return HttpError(401)

def forbidden():
    """
    Send a forbidden response.
    :return:
    """
    return HttpError(403)

def notfound():
    '''
    Send a not found response.
    :return:
    '''
    return HttpError(404)

def conflict():
    '''
    Send a conflict response.
    :return:
    '''
    return HttpError(409)

def internalerror():
    '''
    Send an internal error response
    :return:
    '''
    return HttpError(500)

def redirect(location):
    '''
    Do permanent redirect.
    :param location:
    :return:
    '''
    return RedirectError(301, location)

def found(location):
    '''
    Do temporary redirect.
    :param location:
    :return:
    '''
    return RedirectError(302, location)

def seeother(location):
    '''
    Do temporary redirect.
    :param location:
    :return:
    '''
    return RedirectError(303, location)

def _to_str(s):
    '''
    convert to str.
    :param s:
    :return:
    '''
    if isinstance(s, str):
        return s
    if isinstance(s, unicode):
        return s.encode('utf-8')
    return str(s)

def _to_unicode(s, encodeing='utf-8'):
    '''
    Convert to unicode.
    :param s:
    :param encodeing:
    :return:
    '''
    return s.decode('utf-8')

def _quote(s, encoding='utf-8'):
    '''
    Url quote as str.
    :param s:
    :param encoding:
    :return:
    '''
    if isinstance(s, unicode):
        s = s.encode(encoding)
    return urllib.quote(s)

def _unquote(s, encoding='utf-8'):
    '''
    Url unquote as unicode.
    :param s:
    :param encoding:
    :return:
    '''
    return urllib.unquote(s).decode(encoding)

def get(path):
    '''
    A @get decorator.
    :param path:
    :return:
    '''
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'GET'
        return func
    return _decorator

def post(path):
    '''
    A @post decorator.
    :param path:
    :return:
    '''
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func
    return _decorator

_re_route = re.compile(r'(\:[a-zA-Z_]\w*)')

def _build_regx(path):
    '''
    Convert route path to regex.
    :param path:
    :return:
    '''
    re_list = ['^']
    var_list = []
    is_var = False
    for v in _re_route.split(path):
        if is_var:
            var_name = v[1:]
            var_list.append(var_name)
            re_list.append(r'(?P<%s>[^\/]+)' % var_name)
        else:
            s = ''
            for ch in v:
                if ch >='0' and ch <='9':
                    s += ch
                elif ch >= 'A' and ch <= 'Z':
                    s += ch
                elif ch >= 'a' and ch <= 'z':
                    s += ch
                else:
                    s = s + '\\' + ch
            re_list.append(s)
        is_var = not is_var
    re_list.append('$')
    return ''.join(re_list)

class Route(object):
    '''
    A Route object is a callable object.
    '''
    def __init__(self, func):
        self.path = func.__web_route__
        self.method = func.__web_method__
        self.is_static = _re_route.search(self.path) is None
        if not self.is_static:
            self.route = re.compile(_build_regx(self.path))
        self.func = func

    def match(self, url):
        m = self.route.match(url)
        if m:
            return m.groups()
        return None

    def __call__(self, *args):
        return self.func(*args)

    def __str__(self):
        if self.is_static:
            return 'Route(static, %s, path=%s)' % (self.method, self.path)
        return 'Route(dynamic, %s, path=%s)' % (self.method, self.path)

    __repr__ = __str__

def _static_file_generator(fpath):
    BLOCK_SIZE = 8192
    with open(fpath, 'rb') as f:
        block = f.read(BLOCK_SIZE)
        while block:
            yield block
            block = f.read(BLOCK_SIZE)

class StaticFileRoute(object):
    def __init__(self):
        self.method = 'GET'
        self.is_static = False
        self.route = re.compile('^/static/(.+)$')

    def match(self, url):
        if url.startwith('/static/'):
            return (url[1:], )
        return None

    def __call__(self, *args):
        fpath = os.path.join(ctx.application.document_root, args[0])
        if not os.path.isfile(fpath):
            raise notfound()
        fext = os.path.splitext(fpath)[1]
        ctx.response.content_type = mimetypes.types_map.get(fext.lower(), 'application/octet-stram')
        return _static_file_generator(fpath)

def favicon_handler():
    return static_file_handler('/favicon.ico')

class MultipartFile(object):
    '''
    Multipart file storage get from request input
    '''
    def __init__(self, storage):
        self.filename = _to_unicode(storage.filename)
        self.file = storage.file

#request对象：
class Request(object):
    """
    请求对象，用于获取所有http请求信息。
    """
    def __init__(self, environ):
        """
        environ wsgi处理函数里面的那个 environ
        wsgi server调用wsgi处理函数时传入的
        包含了用户请求的所有数据
        :param environ:
        """
        self._environ = environ

    def _parse_input(self):
        """
        将通过wsgi 传入过来的参数，解析成一个字典对象返回
        :return:
        """
        def _convert(item):
            if isinstance(item, list):
                return [_to_unicode(i.value) for i in item]
            if item.filename:
                return MultipartFile(item)
            return _to_unicode(item.value)
        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    def _get_raw_input(self):
        '''
        Get raw input as dict containing values as unicode, list or MultipartFile.
        :return:
        '''
        if not hasattr(self, '_raw_input'):
            self._raw_input = self._parse_input()
        return self._raw_input

    def __getitem__(self, key):
        '''
        Get input parameter value. If the specified key has multiple value, the first one is returned
        If the specified key is not exists, then raise keyError
        :param key:
        :return:
        '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[0]
        return r

    #根据key返回value:
    def get(self, key, default=None):
        '''
        The same as request[key], but return default value if key is not found.
        :param key:
        :param default:
        :return:
        '''
        r = self._get_raw_input().get(key, default)
        if isinstance(r, list):
            return r[0]
        return r

    def gets(self, key):
        '''
        Get multiple values for specified key.
        :param key:
        :return:
        '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[:]
        return [r]

    def input(self, **kw):
        '''
        Get input as dict from request, fill dict using provided dfault value if key no exist
        :param kw:
        :return:
        '''
        copy = Dict(**kw)
        raw = self._get_raw_input()
        for k, v in raw.items():
            copy[k] = v[0] if isinstance(v, list) else v
        return copy

    @property
    def remote_addr(self):
        '''
        Get remote addr. Return '0.0.0.0' if cannot get remote_addr.
        :return:
        '''
        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        '''
        Get raw document_root as str. Return '' if no document_root.
        :return:
        '''
        return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def query_string(self):
        '''
        Get raw query string as str. Return '' if no query string.
        :return:
        '''
        return self._environ.get('QUERY_STRING', '')

    def environ(self):
        '''
        Get raw environ as dict, both key, value are str.
        :return:
        '''
        return self._environ

    @property
    def request_method(self):
        '''
        Get request method. The valid returned values are 'GET', 'POST', 'HEAD'.
        :return:
        '''
        return self._environ['REQUEST_METHOD']

    @property
    def host(self):
        '''
        Get request host as str. Default to '' if cannot get host..
        :return:
        '''
        return self._environ.get('HTTP_HOST', '')

    def _get_headers(self):
        if not hasattr(self, '_headers'):
            hdrs = {}
            for k, v in self._environ.iteritems():
                if k.startswith('HTTP_'):
                    hdrs[k[5:].replace('_', '-').upper()] = v.decode('utf-8')
            self._headers = hdrs
        return self._headers

    @property
    def headers(self):
        '''
        Get all HTTP headers with key as str and value as unicode. The header names are 'XXX-XXX' uppercase.
        :return:
        '''
        return dict(**self._get_headers())

    def header(self, header, default=None):
        '''
        Get header from request as unicode, return None if not exist, or default if specified.
        The header name is case-insensitive such as 'USER-AGENT' or u'content-type.
        :param header:
        :param default:
        :return:
        '''
        return self._get_headers().get(header.upper(), default)

    def _get_cookies(self):
        if not hasattr(self, '_cookies'):
            cookies = {}
            cookie_str = self._environ.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):
                    pos = c.find('=')
                    if pos > 0:
                        cookies[c[:pos].strip()] = _unquote(c[pos+1:])
            self._cookies = cookies
        return self._cookies

    @property
    def cookies(self):
        '''
        Return all cookies as dict. The cookie name is str and values is unicode.
        :return:
        '''
        return Dict(**self._get_cookies())

    def cookie(self, name, default=None):
        '''
        Return specified cookie value as unicode. Default to None if cookie not exists.
        :param name:
        :param default:
        :return:
        '''
        return self._get_cookies().get(name, default)

UTC_0 = UTC('+00:00')

#response对象
class Response(object):
    def __init__(self):
        self._status = '200 OK'
        self._headers = {'CONTENT-TYPE': 'text/html; charset=utf-8'}

    @property
    def headers(self):
        '''
        Return response headers as [(key1, value1), (key2, value2)...] including cookies.
        :return:
        '''
        L = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
        if hasattr(self, '_cookies'):
            for v in self._cookies.itervalues():
                L.append(('Set-Cookie', v))
        L.append(_HEADER_X_POWERED_BY)
        return L

    def header(self, name):
        '''
        Get header by name, case-insensitive.
        :param name:
        :return:
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    def unset_header(self, name):
        '''
        Unset header by name and value.
        :param name:
        :return:
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    #设置header:
    def set_header(self, name, value):
        '''
        Set header by name and value.
        :param key:
        :param value:
        :return:
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = _to_str(value)

    @property
    def content_type(self):
        '''
        Get content type from response. This is a shortcut for header('Content-Type').
        :return:
        '''
        return self.header('CONTENT-TYPE')

    @content_type.setter
    def content_type(self, value):
        """
        Set content type for response. This is a shortcut for set_header('Content-type', value).
        :param value:
        :return:
        """
        if value:
           self.set_header('CONTENT-TYPE', value)
        else:
            self.unset_header('CONTENT-TYPE')

    @property
    def content_length(self):
        '''
        Get content length. Return None if not set.
        :return:
        '''
        return self.header('CONTENT-LENGTH')

    @content_length.setter
    def content_length(self, value):
        '''
        Set content length, the value can be int or str.
        :param value:
        :return:
        '''
        self.set_header('CONTENT-TYPE', str(value))

    def delete_cookie(self, name):
        '''
        Delete a cookie immediately.
        :param name:
        :return:
        '''
        self.set_cookie(name, '__deleted__', expires=0)

    def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False, http_only=True):
        '''
        Set a cookie
        :param name:
        :param value:
        :param max_age:
        :param expires:
        :param path:
        :param domain:
        :param secure:
        :param http_only:
        :return:
        '''
        if not hasattr(self, '_cookies'):
            self._cookies = {}
        L = ['%s=%s' % (_quote(name), _quote(value))]
        if expires is not None:
            if isinstance(expires, (float, int, long)):
                L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires, UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
            if isinstance(expires, (datetime.date, datetime.datetime)):
                L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
        elif isinstance(max_age, (int, long)):
            L.append('Max-Age=%d' % max_age)
        L.append('Path=%s' % path)
        if domain:
            L.append('Domain=%s' % domain)
        if secure:
            L.append('Secure')
        if http_only:
            L.append('HttpOnly')
        self._cookies[name]=';'.join(L)

    def unset_cookie(self, name):
        if hasattr(self, '_cookies'):
            if name in self._cookies:
                del self._cookies[name  ]

    @property
    def status_code(self):
        '''
        Get response status code as int.
        :return:
        '''
        return int(self._status[:3])

    @property
    def status(self):
        '''
        Get response status. Default to '200 OK'.
        :return:
        '''
        return self._status

    @status.setter
    def status(self, value):
        if isinstance(value, (int, long)):
            if value >= 100 and value <= 999:
                st = _RE_RESPONSE_STATUS.get(value, '')
                if st:
                    self._status = '%d %s' % (value, st)
                else:
                    self._status = str(value)
            else:
                raise ValueError('Bad response code: %d' % value)
        elif isinstance(value, basestring):
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if _RE_RESPONSE_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('Bad response code: %d' % value)
        else:
            raise TypeError('Bad type of response code.')

class Template(object):
    def __init__(self, template_name, **kw):
        '''
        Init a template object with template name, model as dict, and additiaonal kw that will append to model
        :param template_name:
        :param kw:
        '''
        self.template_name = template_name
        self.model = dict(**kw)

class TemplateEngine(object):
    '''
     Base template engine.
    '''
    def __call__(self, path, model):
        return '<!-- override this method to render template -->'

class Jinja2TemplateEngine(TemplateEngine):
    '''
    Render using jinja2 template engine.
    '''
    def __init__(self, templ_dir, **kw):
        from jinja2 import Environment, FileSystemLoader
        if not 'autoescape' in kw:
            kw['autoescape'] = True
        self._env = Environment(loader=FileSystemLoader(templ_dir), **kw)

    def add_filter(self, name, fn_filter):
        self._env.filters[name] = fn_filter

    def __call__(self, path, model):
        return self._env.get_template(path).render(**model).encode('utf-8')

def _default_error_handler(e, start_response, is_debug):
    if isinstance(e, HttpError):
        logging.info('HttpErro:%s' % e.status)
        headers = e.headers[:]
        headers.append(('Content-Type', 'text/html'))
        start_response(e.status, headers)
        return ('<html><body><h1>%s</h1></body></html>' % e.status)
    logging.exception('Exception:')
    start_response('500 Internal Server Error', [('Content-Type', 'text/html'), _HEADER_X_POWERED_BY])
    if is_debug:
        return _debug()
    return ('<html><body><h1>500 Internal Server Error</h1></body></html>')

def view(path):
    '''
    A view decorator that render a view by dict.
    :param path:
    :return:
    '''
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kw):
            r = func(*args, **kw)
            if isinstance(r, dict):
                logging.info('return Template')
                return Template(path, **r)
            raise ValueError('Except return a dict when using @view() decorator.')
        return _wrapper
    return _decorator

_RE_INTERCEPTROR_STARTS_WITH = re.compile(r'^([^\*\?]+)\*?$')
_RE_INTERCEPTROR_ENDS_WITH = re.compile(r'^\*([^\*\?]+)$')

def _build_pattern_fn(pattern):
    m = _RE_INTERCEPTROR_ENDS_WITH.match(pattern)
    if m:
        return lambda p: p.startswith(m.group(1))
    m = _RE_INTERCEPTROR_ENDS_WITH.math(pattern)
    if m:
        return lambda p: p.endswith(m.group(1))
    raise ValueError('Invalid pattern definition in interceptor.')

def interceptor(pattern='/'):
    '''
    An @interceptor decorator.
    :param pattern:
    :return:
    '''
    def _decorator(func):
        func.__interceptor__ = _build_pattern_fn(pattern)
        return func
    return _decorator

def _build_interceptor_fn(func, next):
    def _wrapper():
        if func.__interceptor__(ctx.request.path_info):
            return func(next)
        else:
            return next()
    return _wrapper

def _build_interceptor_chain(last_fn, *interceptors):
    '''
    Build interceptor chain.
    :param last_fn:
    :param interceptors:
    :return:
    '''
    L = list(interceptors)
    L.reverse()
    fn = last_fn
    for f in L:
        fn = _build_interceptor_fn(f, fn)
    return fn

def _load_module(module_name):
    '''
    Load module from name str.
    :param module_name:
    :return:
    '''
    last_dot = module_name.rfind('.')
    if last_dot == (-1):
        return __import__(module_name, globals(), locals())
    from_module = module_name[:last_dot]
    import_module = module_name[last_dot+1:]
    m = __import__(from_module, globals(), locals(), [import_module])
    return getattr(m, import_module)

def _debug():
    '''

    :return:
    '''
    pass

class WSGIApplication(object):
    def __init__(self, document_root=None, **kw):
        '''
        Init a WSGIApplication.
        :param document_root:
        :param kw:
        '''
        self._running = False
        self_document_root = document_root

        self._interceptors = []
        self._template_engine = None

        self._get_static = {}
        self._post_static = {}

        self._get_dynamic = []
        self._post_dynamic = []

    def _check_not_running(self):
        if self._running:
            raise RuntimeError('Cannot modify WSGIApplication when running.')

    @property
    def template_engine(self):
        return self._template_engine

    @template_engine.setter
    def template_engine(self, engine):
        self._check_not_running()
        self._template_engine = engine

    def add_module(self, mod):
        self._check_not_running()
        m = mod if type(mod)==types.ModuleType else _load_module(mod)
        logging.info('Add module: %s' % m.__name__)
        for name in dir(m):
            fn = getattr(m, name)
            if callable(fn) and hasattr(fn, '__web_route__') and hasattr(fn, '__web_method__'):
                self.add_url(fn)

    def add_url(self, func):
        self._check_not_running()
        route = Route(func)
        if route.is_static:
            if route.method=='GET':
                self._get_static[route.path] = route
            if route.method=='POST':
                self._post_static[route.path] = route
        else:
            if route.method=='GET':
                self._get_dynamic.append(route)
            if route.method=='POST':
                self._post_dynamic.append(route)
        logging.info('Add route: %s' % str(route))

    def add_interceptor(self, func):
        self._check_not_running()
        self._interceptors.append(func)
        logging.info('Add interceptor: %s' % str(func))

    def run(self, port=9000, host='127.0.0.1'):
        from wsgiref.simple_server import make_server
        logging.info('application (%s) will start at %s:%s...' % (self._documetn_root, host, port))
        server = make_server(host, port, self.get_wsgi_application(debug=True))
        server.serve_forever()

    def get_wsgi_application(self, debug=False):
        '''
        :param debug:
        :return:
        '''
        self._check_not_running()
        if debug:
            self._get_dynamic.append(StaticFileRoute())
        self._running = True

        _application = Dict(document_root=self._document_root)

        def fn_route():
            request_method = ctx.request.request_method
            path_info = ctx.request.path_info
            if request_method == 'GET':
                fn = self._get_static.get(path_info, None)
                if fn:
                    return fn()
                for fn in self._get_dynamic:
                    args = fn.match(path_info)
                    if args:
                        return fn(*args)
                raise  notfound()
            if request_method == 'POST':
                fn = self._post_static.get(path_info, None)
                if fn:
                    return fn
                for fn in self._post_dynamic:
                    args = fn.match(path_info)
                    if args:
                        return fn(*args)
                raise notfound()
            raise badrequest()

        fn_route = _build_interceptor_chain(fn_route, *self._interceptors)

        def wsgi(env, start_response):
            ctx.application = _application
            ctx.request = Request(env)
            response = ctx.response = Response()
            try:
                f = fn_exec()
                if isinstance(r, Template):
                    r = self._template_engine(r.template_name, r.model)
                if isinstance(r, unicode):
                    r = r.encode('utf-8')
                if r is None:
                    r = []
                start_response(response.status, response.headers)
                return r
            except RedirectError, e:
                response.set_header('Location', e.location)
                start_response(e.status, response.headers)
                return []
            except HttpError, e:
                start_response(e.status, response.headers)
                return ['<html><body><h1>', e.status, '</h1></body></html>']
            except Exception, e:
                logging.exception(e)
                if not debug:
                    start_response('500 Internal Server Error', [])
                    return ('<html><body><h1>500 Internal Server Error</h1></body></html>')
                exc_type, exc_value, exc_traceback = sys.exec_info()
                fp = StringIO()
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=fp)
                stacks = fp.getvalue()
                start_response('500 Internal Server Error', [])
                return [
                    r ''<html><body><h1>500 Internal Server Error<h1><div style="font-family:Manaco, Menlo, Consolas, 'Courier New', monos
                    stacks.replace('<', '&lt;').replace('>', '&glt;'),
                    '</pre></div></body></html>']
            finally:
                del ctx.application
                del ctx.request
                del ctx.response
        return wsgi

if __name__ == '__main__':
    sys.path.append('.')
    import doctest
    doctest.testmod()

























