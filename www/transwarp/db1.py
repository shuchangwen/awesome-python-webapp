#/usr/bin/env python
#_*_ coding:utf-8 _*_
import functools
import logging
import threading
import time
import uuid

engine = None

def next_id(t=None):
    """
    生成一个唯一id 由当前时间 + 随机数（由伪随机数得来）拼接得到
    :param t:
    :return:
    """
    if t is None:
        t = time.time()
    return '%015d%s000' % (int(t * 1000), uuid.uuid4().hex)

def _profiling(start, sql = ''):
    """
    用于剖析sql的执行时间
    :param start:
    :param sql:
    :return:
    """
    t = time.time() - start
    if t > 0.1:
        logging.warning('[PROFILING] [DB] %s: %s' % (t, sql))
    else:
        logging.info('[PROFILING] [DB] %s: %s' % (t, sql))


def create_engine(user, password, database, host='127.0.0.1', port=3306, **kw):
    """
    db模型的核心函数，用于连接数据库，生成全局对象engine,
    engine对象持有数据库连接
    :param user:
    :param password:
    :param database:
    :param host:
    :param port:
    :param kwargs:
    :return:
    """
    import mysql.connector
    global engine
    if engine is not None:
        raise DBError('Engine is already initialized.')
    params = dict(user=user, password=password, host=host, port=port)
    defaults = dict(use_unicode=True, charset='utf8', collation='utf8_general_ci', autocommit=True)
    for k, v in defaults.iteritems():
        params[k] = kw.pop(k, v)
    params.update(kw)
    params['buffered'] = True
    engine = _Engine(lambda: mysql.connector.connect(**params))
    #logging.info("Engine is None: %s" % (engine is None))
    # test connection...
    logging.info('Init mysql engine <%s> ok.' % hex(id(engine)))

def connection():
    """
    db模块核心函数，用于获取一个数据库连接
    :return:
    """
    return _ConnectionCtx()

def with_connection(func):
    """
    设计一个装饰器 替换with语法
    :param func:
    :return:
    """
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        with _ConnectionCtx():
            return func(*args, **kw)
    return _wrapper

def transaction():
    """
    db模块核心函数 用于实现事物功能
    :return:
    """
    return _TransactionCtx()

def with_transaction(func):
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        start = time.time()
        with _TransactionCtx():
            func(*args, **kw)
        _profiling(start)
    return _wrapper

@with_connection
def _select(sql, first, *args):
    """
    执行SQL,
    :param sql: 返回一个结果或者多个结果组成的列表
    :param first:
    :param args:
    :return:
    """
    global _db_ctx
    cursor = None
    sql = sql.replace('?', '%s')
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        if cursor.description:
            names = [x[0] for x in cursor.description]
        if first:
            values = cursor.fetchone()
            if not values:
                return None
            return Dict(names, values)
        return [Dict(names, x) for x in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()

def select_one(sql, *args):
    """
    执行sql 仅返回一个结果
    :param sql:
    :param args:
    :return:
    """
    return _select(sql, True, *args)

def select_int(sql, *args):
    """
    执行一个sql, 返回一个数值
    :param sql:
    :param args:
    :return:
    """
    d = _select(sql, True, *args)
    if len(d) != 1:
        raise MultiColumnsError('Expect only one column.')
    return d.values()[0]

def select(sql, *args):
    """
    执行sql以列表形式返回结果
    :param sql:
    :param args:
    :return:
    """
    return _select(sql, False, *args)

@with_connection
def _update(sql, *args):
    """
    执行update语句，返回update的行数
    :param sql:
    :param args:
    :return:
    """
    global _db_ctx
    cursor = None
    sql = sql.replace('?', '%s')
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        r = cursor.rowcount
        if _db_ctx.transactions == 0:
            #no transaction environment:
            logging.info('auto commit')
            _db_ctx.connection.commit()
        return r
    finally:
        if cursor:
            cursor.close()

def update(sql, *args):
    """
    执行update语句，返回update的行数
    :param sql:
    :param args:
    :return:
    """
    return _update(sql, *args)

def insert(table, **kwargs):
    """
    执行insert 语句
    :param table:
    :param kwargs:
    :return:
    """
    cols, args = zip(*kwargs.iteritems())
    sql = 'insert into `%s` (%s) values (%s)' % (table, ','.
                join(['`%s`' % col for col in cols]), ','.
                join(['?' for i in range(len(cols))]))
    return _update(sql, *args)

class Dict(dict):
    """
    字典对象
    实现一个简单的可以通过属性访问的字典，比如x.key = value
    """
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

class DBError(Exception):
    pass

class MultiColumnsError(DBError):
    pass

class _Engine(object):
    """
    数据库引擎对象
    用于保存db模块的核心函数:create_engine创建出来的数据库连接
    """
    def __init__(self, connect):
        self._connect = connect
    def connect(self):
        return self._connect()

class _LasyConnection(object):
    """
    惰性连接对象
    仅当需要cursor对象时，才连接数据库，获取连接
    """
    def __init__(self):
        self.connection = None

    def cursor(self):
        if self.connection is None:
            _connection = engine.connect()
            logging.info('[CONNECTION] [OPEN] connection <%s>...' % hex(id(_connection)))
            self.connection = _connection
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def cleanup(self):
        if self.connection:
            _connection = self.connection
            self.connection = None
            logging.info('[CONNECTION] [CLOSE] connection <%s>...' % hex(id(connection)))
            _connection.close()


class _DbCtx(threading.local):
    """
    db模块的核心对象, 数据库连接的上下文对象，负责从数据库获取和释放连接
    取得的连接是惰性连接对象，因此只有调用cursor对象时，才会真正获取数据库连接
    该对象是一个 Thread local对象，因此绑定在此对象上的数据 仅对本线程可见
    """
    def __init__(self):
        self.connection = None
        self.transactions = 0

    def is_init(self):
        """
        返回一个布尔值，用于判断此对象的初始状态
        :return:
        """
        return self.connection is not None

    def init(self):
        """
        初始化连接的上下文对象，获得一个惰性连接对象
        :return:
        """
        logging.info('open lazy connection...')
        self.connection = _LasyConnection()
        self.transactions = 0

    def cleanup(self):
        """
        清理连接对象，关闭连接
        :return:
        """
        self.connection.cleanup()
        self.connection = None

    def cursor(self):
        """
        获取cursor对象，真正取得数据库连接
        :return:
        """
        return self.connection.cursor()

#thread-local db context:
_db_ctx = _DbCtx()

class _ConnectionCtx(object):
    """
     因为_DbCtx实现了连接的 获取和释放，但是并没有实现连接
    的自动获取和释放，_ConnectCtx在 _DbCtx基础上实现了该功能，
    因此可以对 _ConnectCtx 使用with 语法，比如：
    with connection():
        pass
        with connection():
            pass
    """
    def __enter__(self):
        """
        获取一个惰性连接对象
        :return:
        """
        global _db_ctx
        self.should_cleanup = False
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.should_cleanup = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        释放连接
        """
        global _db_ctx
        if self.should_cleanup:
            _db_ctx.cleanup()



class _TransactionCtx(object):
    """
     事务嵌套比Connection嵌套复杂一点，因为事务嵌套需要计数，
    每遇到一层嵌套就+1，离开一层嵌套就-1，最后到0时提交事务
    """
    def __enter__(self):
        global _db_ctx
        self.should_close_conn = False
        if not _db_ctx.is_init():
            #needs open a connection first:
            _db_ctx.init()
            self.should_close_conn = True
        _db_ctx.transactions = _db_ctx.transactions + 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _db_ctx
        _db_ctx.transactions = _db_ctx.transactions - 1
        try:
            if _db_ctx.transactions == 0:
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
        finally:
            if self.should_close_conn:
                _db_ctx.cleanup()

    def commit(self):
        global  _db_ctx
        logging.info('commit transaction...')
        try:
            _db_ctx.connection.commit()
        except:
            _db_ctx.connection.rollback()
            raise

    def rollback(self):
        global _db_ctx
        logging.warning('rollback transaction...')
        _db_ctx.connection.rollback()
        logging.info('rollback ok.')

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    create_engine('www-data', 'www-data', 'test')
    update('drop table if exists user')
    update('create table user(id int primary key, name text, email text, passwd text, last_modified real)')
    import doctest
    doctest.testmod()












