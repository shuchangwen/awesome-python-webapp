#!/usr/bin/env python
# coding=utf-8
import sys
sys.path.append('..')

from www.transwarp.orm import Model, StringField, IntegerField
from www.transwarp.db import *
import logging

class User(Model):
    __table__ = 'user'
    id = IntegerField(primary_key=True)
    name = StringField()

user = User(id=123, name='Michael')
logging.basicConfig(level=logging.DEBUG)
create_engine('www-data', 'www-data', 'test')
user.insert()