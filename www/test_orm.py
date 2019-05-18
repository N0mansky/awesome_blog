from www import orm
from www.model import User
import asyncio


async def test(loop):
    await orm.create_pool(loop=loop, host='192.168.122.3', user='www-data', password='www-data', db='awesome')
    u = User(name='Test', email='test.email@example.com', passwd='123456', image='about:blank')
    await u.save()


loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
loop.close()
