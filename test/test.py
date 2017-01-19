#!/usr/bin/env python
# coding=utf-8
import sys
sys.path.append('..')

from www.transwarp.orm import Model, StringField, IntegerField
from www.models import *
from www.transwarp.db import *
import logging

# class User(Model):
#     __table__ = 'user'
#     id = IntegerField(primary_key=True)
#     name = StringField()

# user = User(id=123, name='Michael')
# logging.basicConfig(level=logging.DEBUG)
# create_engine('www-data', 'www-data', 'test')
# user.insert()

create_engine('www-data', 'www-data', 'awesome')
user = User.find_first('where email=?', 'admin@example.com')
print user;
blog_name="习近平在联合国日内瓦总部的演讲(全文)"
blog_summary="新华社日内瓦1月18日电 国家主席习近平18日在联合国日内瓦总部发表了题为《共同构建人类命运共同体》的主旨演讲。"
blog_content="中华人民共和国主席习近平尊敬的联合国大会主席汤姆森先生，" \
             "尊敬的联合国秘书长古特雷斯先生，尊敬的联合国日内瓦总部总干事穆勒先生，" \
             "女士们，先生们，朋友们：详情参考：http://news.ifeng.com/a/20170119/50598658_0.shtml"
blog = Blog(user_id=user.id, user_name=user.name, user_image=user.image, name=blog_name,summary=blog_summary, content=blog_content)
blog.insert()
