"""
This module is encapsulation of aiohttp.web
Step 1: Mapping all path with RequestHandler instance and specific function
Step 2: RequestHandler is the handler to deal with request parameters before invoke handler function
Step 3: RequestHandler was encapsulated handler function

:author: yangby
:date:   2019-03-17
"""
import asyncio
import functools
import inspect
import logging
import os
from urllib import parse

from aiohttp import web

from apis import APIError


def get(path):
    """
    Define decorator @get('/path')
    :param path:  url path
    :return:  Handler of path
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper

    return decorator


def post(path):
    """
    Define decorator @post('/path')
    :param path:  url path
    :return:  Handler of path
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'POST'
        wrapper.__route__ = path

        return wrapper

    return decorator


def has_request_arg(fn):
    """
    Find request paramter in function and determine
    request type
    :param fn:
    :return: boolean
    """
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (
                param.kind != inspect.Parameter.VAR_POSITIONAL
                and param.kind != inspect.Parameter.KEYWORD_ONLY
                and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError(
                'request parameter must be the last named parameter in function: '
                '{}{}'.format(fn.__name__, sig))

    return found


def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


class RequestHandler(object):
    """This class is parse request parameters,then assigning to handlers to deal """

    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    async def __call__(self, request):
        kw = None
        """1. Obtain form params from POST or GET request
           2. Convert params to dict save as kw 
        """
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest(text='Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest(text='JSON body must be object')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    # return web.HTTPBadRequest()
                    return web.HTTPBadRequest(text='Unsupported Content-Type:{}'.format(ct))
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                # Remove all unamed kw:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
                # Check named arg:
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args:{}'.format(k))
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        if self._required_kw_args:
            for name in self._required_kw_args:
                if name not in kw:
                    return web.HTTPBadRequest(text='Missing argument:{}'.format(name))
        logging.info('Call with args:{}'.format(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static {} => {}'.format('/static/', path))


def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    # if path is None or method is None:
    #    raise ValueError('@get or @post not defined in {}'.format(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('Add route {} {} => {}({})'.format(method, path, fn.__name__,
                                                    ','.join(inspect.signature(fn).parameters.keys())))
    # app.router.add_route(method, path, RequestHandler(app, fn))
    handle = RequestHandler(app, fn)
    if method == 'GET':
        app.router.add_get(path, handle)
    elif method == 'POST':
        app.router.add_post(path, handle)
    # app.router.add_route(method, path, RequestHandler(app, fn))


def add_routes(app, modules):
    """
    Scanning modules and mapping url path with function
    :param app:
    :param modules:
    :return:
    """
    n = modules.rfind('.')
    if n == -1:
        mod = __import__(modules, globals(), locals())
    else:
        name = modules[n + 1:]
        mod = getattr(__import__(modules[:n], globals(), locals(), [name]), name)
    alls = dir(mod)
    for attr in alls:
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)
