import base64
import datetime
import re
from typing import Optional, Union

from bs4 import BeautifulSoup as Souper
from smartify import E

from YongShuoX.base import _Dictifier, YSError


@E.register()
class LockerE:
    LOCKED = E("尚未认证")
    AUTHED = E("已经认证")
    CAPTCHA = E("需要验证码")


class YSLocker(_Dictifier):
    """认证类"""

    def __init__(self, client, password=None):
        """
        :param client: 认证对象
        :param password: 认证密钥
        """
        self.password = password or ''
        self.ok = False
        from .node import YS, YSMainFolder
        self.client = client  # type: Union[YS, YSMainFolder]

        if password:
            self._enok()

    def __str__(self):
        return str(self.ok)

    def _enok_uri(self):
        raise YSError.NOT_IMPLEMENTED

    def _enok(self):
        raise YSError.NOT_IMPLEMENTED

    def auth(self, password):
        """密钥认证"""
        if not self.ok:
            self.password = password
            self._enok()
        return self.ok

    def d(self):
        return self.dictify('ok', 'password')

    def reset(self):
        self.ok = False
        if self.password:
            self._enok()


class YSFolderLocker(YSLocker):
    """根目录认证器"""

    def __init__(self, **kwargs):
        super(YSFolderLocker, self).__init__(**kwargs)

    def _enok_uri(self):
        return '{3}/f_ht/ajcx/mlrz.aspx?cz=Kqmmpd&mlbh={0}&kqmm={2}&yzm=&_dlmc={1}&_dlmm={4}'. \
            format(self.client.id,
                   self.client.core.bucket,
                   self.password,
                   self.client.core.api_host,
                   self.client.core.token)

    def _enok(self):
        if self.ok:
            raise LockerE.AUTHED

        data = self.client.core.sess.get(self._enok_uri(), decode=True)
        self.ok = data.find('"xzzt":true') >= 0


class YSAdminLocker(YSLocker):
    """管理员认证器"""

    def __init__(self, **kwargs):
        super(YSAdminLocker, self).__init__(**kwargs)

    def _enok_uri(self):
        return '{1}/f_ht/ajcx/gly.aspx?cz=dl&yzm=&_dlmc={0}&_dlmm={2}'.format(
            self.client.bucket, self.client.api_host, self.client.token)

    def _enok(self):
        if self.ok:
            raise LockerE.AUTHED

        data = self.client.sess.post(self._enok_uri(), data=dict(glmm=self.password), decode=True)
        self.ok = data.find('bgglzt(true)') >= 0


class YSEntranceLocker(YSLocker):
    """访问认证器"""

    def __init__(self, **kwargs):
        super(YSEntranceLocker, self).__init__(**kwargs)

        self.require_captcha = None  # type: Optional[bool] # 是否需要验证码
        self.captcha_image = None  # type: Optional[str] # 验证码图片
        self.captcha = None  # type: Optional[str] # 用户输入的验证码字符串
        self.__EVENTVALIDATION = self.__VIEWSTATE = None  # 表单参数
        self.reset()

    def _readable_captcha_image(self):
        if self.captcha_image:
            return base64.b64encode(self.captcha_image).decode()

    def d(self):
        dict_ = super(YSEntranceLocker, self).d()
        dict_.update(self.dictify('require_captcha', 'captcha_image'))
        return dict_

    def reset(self):
        """重新监测"""
        self._check_if_require_captcha()
        return self

    def _captcha_uri(self):
        return '{0}/ys_vf_img.aspx?lx={1}dlmm&sj={2}'.format(
            self.client.host, self.client.bucket, datetime.datetime.now().timestamp())

    def _enok_uri(self):
        return '{0}/login.aspx?d={1}'.format(self.client.host, self.client.bucket)

    def _extract_host_soup(self, soup: Souper):
        if soup.find(id='kjbt'):
            self.ok = True
            self.captcha = None
            self.captcha_image = None
            self.__VIEWSTATE = None
            self.__EVENTVALIDATION = None
            matcher = re.search("_dlmm:'(.*?)'", str(soup))
            self.client.token = matcher.group(1) if matcher else ''
            return

        self.ok = False
        captcha_box = soup.find(id='yzm_tr')
        if captcha_box.get('style') == 'display: none;':
            self.require_captcha = False
        else:
            self.require_captcha = True
            self.captcha_image = self.client.sess.get(self._captcha_uri(), decode=False)

        self.__VIEWSTATE = soup.find(id='__VIEWSTATE').get('value')
        self.__EVENTVALIDATION = soup.find(id='__EVENTVALIDATION').get('value')

    def _check_if_require_captcha(self):
        soup = self.client.sess.get(self.client.host, soup=True)  # type: Souper
        self._extract_host_soup(soup)

        if self.ok:
            self.require_captcha = False

    def _enok(self):
        if self.require_captcha and not self.captcha:
            raise LockerE.CAPTCHA

        if self.ok:
            raise LockerE.AUTHED

        form_data = dict(
            __VIEWSTATE=self.__VIEWSTATE,
            __EVENTVALIDATION=self.__EVENTVALIDATION,
            b_dl='登陆',
            te_yzm=self.captcha,
            teqtbz=self.password,
        )

        soup = self.client.sess.post(self._enok_uri(), form_data, soup=True)
        self._extract_host_soup(soup)

    def auth(self, password, captcha=None):
        """密钥认证"""
        if not self.ok:
            self.captcha = captcha or self.captcha
            self.password = password
            self._enok()
        return self.ok
