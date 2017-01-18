# test_db.py
#!/usr/bin/env python
#coding = utf-8
import os
import sys
sys.path.append("..")

from www.models import User, Blog, Comment
from www.transwarp.db import *

create_engine(user='www-data', password='www-data', database='awesome')

u = User(name='Administrator', email='admin@example.com', password='123456', image='about:blank')
u.insert()
u = User(name='Michael', email='michael@example.com', password='123456', image='about:blank')
u.insert()
u = User(name='Test', email='test@example.com', password='123456', image='about:blank')
u.insert()
os._exit(0)
# print 'new user id:', u.id
#
# u1 = User.find_first('where email=?', 'test@example.com')
# print 'find user\'s name:', u1.name
#
# u1.delete()
#
# u2 = User.find_first('where email=?', 'test@example.com')
# print 'find user:', u2

