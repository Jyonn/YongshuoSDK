import json
from typing import Callable

import requests
from bs4 import BeautifulSoup as Souper


class _Log:
    """日志记录"""
    records = []

    def __init__(self, text):
        _Log.records.append(text)


class _Symbol:
    """唯一标识符"""

    def __init__(self, text=None):
        self._text = text or ''

    def __str__(self):
        return self._text


class _Dictifier:
    """类转字典"""

    def dictify(self, *args):
        """
        字典输出
        :param args: 需要输出的属性
        :return: 属性对应的字典
        """
        dict_ = {}
        for arg in args:
            readable_func = getattr(self, '_readable_{0}'.format(arg), None)
            if callable(readable_func):
                dict_[arg] = readable_func()
            else:
                dict_[arg] = getattr(self, arg, None)
        return dict_


class _Fetcher:
    def __init__(self):
        self.sess = requests.Session()

    def reset(self):
        self.sess = requests.Session()
        return self

    @staticmethod
    def request(caller: Callable, url, decode=True, soup=False, jsonify=False, **kwargs):
        with caller(url, **kwargs) as resp:
            data = resp.content
        if decode or soup or jsonify:
            data = data.decode()
            if soup:
                data = Souper(data, 'html.parser')
            if jsonify:
                data = json.loads(data)
        return data

    def get(self, url, **kwargs):
        return self.request(self.sess.get, url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs.update(dict(data=data, json=json))
        return self.request(self.sess.post, url, **kwargs)

    def put(self, url, data=None, **kwargs):
        kwargs.update(dict(data=data))
        return self.request(self.sess.put, url, **kwargs)
