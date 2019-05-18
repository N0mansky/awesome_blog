import logging

from jinja2 import FileSystemLoader, Environment

import orm
from coroweb import add_routes, add_static
from handlers import COOKIE_NAME, cookie2user

logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)

import asyncio, os, json, time
from datetime import datetime
from aiohttp import web


def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        autoescape=kw.get('autoescape', True),
        block_start_string=kw.get('block_start_string', '{%'),
        block_end_string=kw.get('block_end_string', '%}'),
        variable_start_string=kw.get('variable_start_string', '{{'),
        variable_end_string=kw.get('variable_end_string', '}}'),
        auto_reload=kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('set jinjia2 template path: {}'.format(path))
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', kw)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    app['__templating__'] = env


async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: {} {}'.format(request.method, request.path))
        return await handler(request)

    return logger


async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json:{}'.format(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form:{}'.format(request.__data__))
        return await handler(request)

    return parse_data


async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler...')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        elif isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        elif isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        elif isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(body=json.dumps(r,
                                                    ensure_ascii=False,
                                                    default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        elif isinstance(r, int) and 100 <= r < 600:
            return web.Response(r)
        elif isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and 100 <= t < 600:
                return web.Response(t, str(m))
        else:
            resp = web.Response(body=str(r).encode('utf-8'))
            resp.content_type = 'text/plain;charset=utf-8'
            return resp

    return response


async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: {} {}'.format(request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = await cookie2user(cookie_str)
            if user:
                logging.info('set current_user user: {}'.format(user.email))
                request.__user__ = user
            if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
                return web.HTTPFound('/signin')
            return await handler(request)

    return auth


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return '1分钟前'
    if delta < 3600:
        return '{}分钟前'.format(delta // 60)
    if delta < 86400:
        return '{}小时前'.format(delta // 3600)
    if delta < 604800:
        return '{}天前'.format(delta // 86400)
    dt = datetime.fromtimestamp(t)
    return '{}年{}月{}日'.format(dt.year, dt.month, dt.day)


async def init(loop):
    await orm.create_pool(loop=loop, host='192.168.122.3', user='www-data', password='www-data', db='awesome')
    # app = web.Application(loop=loop, middlewares=[
    #     logger_factory, response_factory
    # ])
    app = web.Application(logger=logging.info, middlewares=[logger_factory, response_factory])

    init_jinja2(app, filters=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')
    add_static(app)
    # app_runner = web.AppRunner(app)
    # await app_runner.setup()
    # srv = await loop.create_server(app_runner.server, '127.0.0.1', 9000)
    # srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    # logging.info('server started at http://127.0.0.1:9000...')
    return app


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    web.run_app(init(loop), host='0.0.0.0', port=9000)
    # loop.run_until_complete(init(loop))
    # loop.run_forever()
