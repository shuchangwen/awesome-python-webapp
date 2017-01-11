#/usr/bin/env python
#coding=utf-8

from db import  *

create_engine('www-data', 'www-data', 'test')
# u1 = dict(id=101, name='Alice', email='alice@test.org', passwd='ABC-12345', last_modified=time.time())
# u2 = dict(id=103, name='Sarah', email='sarah@test.org', passwd='ABC-12345', last_modified=time.time())
# print insert('user', **u1)
# print insert('user', **u2)
users = select('select * from user')
print users
u = select_one('select * from user where id = ?', 100)
print u.name
print select_int('select count(*) from user')
print select_int('select count(*) from user where email=?', 'alice@test.org')
print select_int('select count(*) from user where email=?', 'notexist@test.org')
print select_int('select id, name from user where email=?', 'scw@test.org')


