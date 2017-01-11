#!/usr/bin/env python
#_*_ coding=utf-8 _*_
import logging

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
            attrs['__sql__'] = lambda self:__gen_sql




