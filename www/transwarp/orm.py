#!/usr/bin/env python
#_*_ coding=utf-8 _*_
import logging
import db

_triggers = frozenset(['pre_insert', 'pre_update', 'pre_delete'])

def _gen_sql(table_name, mappings):
    """
    类 ==> 表时 生成创建表的sql
    :param table_name:
    :param mappings:
    :return:
    """
    pk = None
    sql = ['-- generating SQL for %s:' % table_name, 'create table `%s` (' %table_name]
    for f in sorted(mappings.values(), lambda x, y: cmp(x._order, y._order)):
        if not hasattr(f, 'ddl'):
            raise StandardError('no ddl in field "%s".' % f)
        ddl = f.ddl
        nullable = f.nullable
        if f.primary_key:
            pk = f.name
        sql.append('    `%s` %s,' % (f.name, ddl) if nullable else '    `%s` %s not null,' % (f.name, ddl))
    sql.append('    primary key(`%s`)' % pk)
    sql.append(');')
    return '\n'.join(sql)

class Field(object):
    """
    保存数据库中的表的 字段属性
    """
    _count = 0

    def __init__(self, **kw):
        self.name = kw.get('name', None)
        self._default = kw.get('default', None)
        self.primary_key = kw.get('primary_key', False)
        self.nullable = kw.get('nullable', False)
        self.updatable = kw.get('updatable', True)
        self.insertable = kw.get('insertable', True)
        self.ddl = kw.get('ddl', '')
        self._order = Field._count
        Field._count += 1

    @property
    def default(self):
        """
        利用getter实现的一个写保护的实例属性
        :return:
        """
        d = self._default
        return d() if callable(d) else d

    def __str__(self):
        """
        返回实例对象的描述信息
        :return:
        """
        s = ['<%s:%s, default(%s), ' % (self.__class__.__name__, self.name, self.ddl, self._default)]
        self.nullable and s.append('N')
        self.updatable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')
        return ''.join(s)

class IntegerField(Field):
    """
    保存Integer类型字段的属性
    """
    def __init__(self, **kw):
        if 'default' not in kw:
            kw['defualt'] = 0
        if 'ddl' not in kw:
            kw['ddl'] = 'bigint'
        super(IntegerField, self).__init__(**kw)

class FloatField(Field):
    """
    保存Float类型字段的属性
    """
    def __int__(self, **kw):
        if 'default' not in kw:
            kw['default'] = 0.0
        if 'ddl' not in kw:
            kw['ddl'] = 'bool'
        super(FloatField, self).__init__(**kw)

class BooleanField(Field):
    """
    保存BooleanField类型字段的属性
    """
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = False
        if not 'ddl' in kw:
            kw['ddl'] = 'bool'
        super(BooleanField, self).__init__(**kw)

class TextFiled(Field):
    """
    保存Text类型字段的属性
    """
    def __init__(self):
        if 'default' not in kw:
            kw['default'] = ''
        if 'ddl' not in kw:
            kw['ddl'] = 'text'
        super(TextFiled, self).__init__(**kw)

class BlobField(Field):
    """
    宝不能Blob类型字段的属性
    """
    def __init__(self, **kw):
        if 'default' not in kw:
            kw['default'] = ''
        if 'ddl' not in kw:
            kw['ddl'] = 'blob'
        super(BlobField, self).__init__()

class VersionField(Field):
    """
    保存Version类型字段的属性
    """
    def __init__(self, name=None):
        super(VersionField, self).__init__(name=name, default=0, ddl='bigint')

class ModelMetaclass(type):
    """
    对类对象动态完成以下动作
    避免修改Model类：
    属性与字段的mapping：
    类和表的mapping
    """
    def __new__(cls, name, bases, attrs):
        #skip base Model class:
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)

        # store all subclasses into
        if not hasattr(cls, 'subclasses'):
            cls.subclasses = {}
        if not name in cls.subclasses:
            cls.subclasses[name] = name
        else:
            logging.warning('Redefine class: %s' % name)

        logging.info('Scan ORMapping %s...' % name)
        mappings = dict()
        primary_key = None
        for k, v in attrs.iteritems():
            if isinstance(v, Field):
                if not v.name:
                    v.name = k
                logging.info('[MAPPING] Found mapping: %s => %s' % (k, v))
                # check duplicate primary key:
                if v.primary_key:
                    if primary_key:
                        raise TypeError('Cannot define more than 1 more primary key in class: %s' % name)
                    if v.updatable:
                        logging.warning('NOTE: change primary key to non-undatable.')
                        v.updatable = False
                    if v.nullable:
                        logging.warning('NOTE: change primary key to non-nullable.')
                        v.nullable = False
                    primary_key = v
                mappings[k] = k
            #check exist of primary key:
            if not primary_key:
                raise TypeError('Primary key not defined in class: %s' % name)
            for k in mappings.iterkeys():
                attrs.pop(k)
            if not '__table__' in attrs:
                attrs['__table__'] = name.lower()
            attrs['__mappings__'] = mappings
            attrs['__primary_key__'] = primary_key
            attrs['__sql__'] = lambda self:_gen_sql(attrs['__table__'], mappings)
            for trigger in _triggers:
                if not trigger in attrs:
                    attrs[trigger] = None
            return type.__new__(cls, name, bases, attrs)

class Model(dict):
    """
    基类，用户在子类中 定义映射关系，因此我们需要动态扫描子类属性，
    从中抽取出了属性， 完成类 <==>表的映射，这里使用metaclass来实现。
    最后将扫描出来的结果保存在类属性
        "__table__" : 表名
        "__mappings__": 字段对象（字段的所有属性，见Field类）
        "__primary_key__":主键字段
        "__sql__": 创建表时执行的sql
    """
    __metaclass__ = ModelMetaclass
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        """
        get时生效，比如a[key], a.get(key)
        get时 返回属性的值
        :param key:
        :return:
        """
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        """
        set时生效， 比如a[key]=value, a={'key1':'value1', 'key2':'value2'}
        set时添加属性
        :param key:
        :param value:
        :return:
        """
        self[key] = value

    @classmethod
    def get(cls, pk):
        """
        Get by primary key.
        :param pk:
        :return:
        """
        d = db.select_one('select * from %s where %s=?' % (cls.__table__, cls.__primary_key__.name), pk)
        return cls(**d) if d else None

    @classmethod
    def find_first(cls, where, *args):
        """
        通过where语句进行条件查询，返回一个查询结果。如果有多个查询结果仅取第一个
        如果没有结果，则返回None
        :param where:
        :param args:
        :return:
        """
        d = db.select_one('select * from %s %s' % (cls.__table__, where), *args)
        return cls(**d) if d else None

    @classmethod
    def find_all(cls, *args):
        """
        查询所有字段，将结果以一个列表返回
        :param args:
        :return:
        """
        L = db.select('select * from `%s`' % cls.__table__)
        return [cls(**d) for d in L]

    @classmethod
    def find_by(cls, where, *args):
        """
        通过where语句进行条件查询，将结果以一个列表返回
        :param where:
        :param args:
        :return:
        """
        L = db.select('select * from `%s` %s' % (cls.__table__, where), *args)
        return [cls(**d) for d in L]

    @classmethod
    def count_all(cls):
        """
        执行select count(pk) from table语句，返回一个数值
        :return:
        """
        return db.select('select count(`%s`) from `%s`' % (cls.__primary_key__.nae, cls.__table__))

    @classmethod
    def count_by(cls, where, *args):
        """
        通过select count(pk) from table where ...语句进行查询，返回一个数值
        :param where:
        :param args:
        :return:
        """
        return db.select_int('select count(`%s`) from `%s` %s' % (cls.__primary_key__.name, cls.__table__, where), *args)

    def update(self):
        """
        如果该行的字段属性有updatable, 代表该字段有被更新
        用于定义的表（继承Model的类）时一个Dict对象，键值会变成实例的属性
        所以可以通过属性来判断 用户是否定义了该字段的值
            如果有属性，就是用用户传入的值
            如果无属性，则调用字段对象的default属性传入
            具体见Field类的default属性
        :return:
        """
        self.pre_update and self.pre_update()
        L = []
        args = []
        for k, v in self.__mappings__.iteritems():
            if v.updatable:
                if hasattr(self, k):
                    arg = getattr(self, k)
                else:
                    arg = v.default
                    setattr(self, k, arg)
                L.append('`%s`=?' % k)
                args.append(arg)
        pk = self.__primary_key__.name
        args.append(getattr(self, pk))
        db.update('updte `%s` set %s where %s=?' % (self.__table__, ','.join(L), pk), *args)
        return self

    def delete(self):
        """
        通过db对象的update接口 执行SQL
        :return:
        """
        self.pre_delete and self.pre_delete()
        pk = self.__primary_key__.name
        args = (getattr(self, pk), )
        db.update('delete from `%s`=?' % (self.__table__, pk), *args)
        return self

    def insert(self):
        """
        通过db对象的insert接口执行SQL
        :return:
        """
        self.pre_insert and self.pre_insert()
        params = {}
        for k, v in self.__mappings__.iteritems():
            if v.insertable:
                if not hasattr(self, k):
                    setattr(self, k, v.default)
                params[v.name] = getattr(self, k)
        db.insert('%s' % self.__table__, **params)
        return self

if __name__ == '__main__':
    logging.basicConfg(level=logging.DEBUG)
    db.create_engine('www-data', 'www-data', 'test')
    db.update('drop table if exists user')
    db.update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
    import doctest
    doctest.testmod()








