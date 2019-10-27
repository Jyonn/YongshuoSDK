import base64
import copy
import datetime
import mimetypes
import os
import re
from typing import List, Union, Optional

import bs4
from bs4 import BeautifulSoup as Souper

from .base import _Symbol, _Dictifier, _Fetcher


class YSLocker(_Dictifier):
    """认证类"""

    def __init__(self, client, password=None):
        """
        :param client: 认证对象
        :param password: 认证密钥
        """
        self.password = password
        self.ok = False
        self.client = client  # type: Union[YS, YSMainFolder]

        if password:
            self._enok()

    def __str__(self):
        return str(self.ok)

    def _enok_uri(self):
        raise NotImplementedError

    def _enok(self):
        raise NotImplementedError

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
            return

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
            return

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
            return

        if self.ok:
            return

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


class YSNodeType:
    """永硕节点类型"""
    FILE = _Symbol()
    FOLDER = _Symbol()
    TEXT = _Symbol()
    LINK = _Symbol()
    COMMENT = _Symbol()


class YSNode(_Dictifier):
    """永硕基本节点"""

    def __init__(self, name, type_: _Symbol, label, core):
        """
        节点构造器
        :param name: 节点名称
        :param type_: 节点类型，应为YSNodeType的其中一类
        :param label: 节点标签
        :param core: 节点所属的永硕网盘类
        """
        self.name = name
        self.type = type_
        self.label = label
        self.core = core  # type: YS

    def __str__(self):
        return self.name

    def _readable_type(self):
        for key in YSNodeType.__dict__:
            type_ = getattr(YSNodeType, key, None)
            if self.type == type_:
                return key
        return self.type

    def d(self):
        return self.dictify('name', 'type', 'label')


class YSIdNode(YSNode):
    """含有ID的永硕基本节点"""

    def __init__(self, id_, **kwargs):
        super(YSIdNode, self).__init__(**kwargs)
        self.id = id_

    def d(self):
        dict_ = super(YSIdNode, self).d()
        dict_.update(self.dictify('id'))
        return dict_


class YSFriendLink(_Dictifier):
    """永硕友情链接类"""

    def __init__(self, name, link):
        """
        :param name: 链接名称
        :param link: 链接地址
        """
        self.name = name
        self.link = link

    def __str__(self):
        return self.name

    def d(self):
        return self.dictify('name', 'link')


class YSComment(YSIdNode):
    """永硕留言类"""

    def __init__(self, face, public, top, reply, reply_as_admin, **kwargs):
        """
        :param face: 留言表情
        :param public: 是否公开
        :param top: 是否置顶
        :param reply: 回复内容
        :param reply_as_admin: 是否以管理员身份回复
        """
        super(YSComment, self).__init__(type_=YSNodeType.COMMENT, **kwargs)
        self.face = face
        self.public = public
        self.top = top
        self.reply = reply
        self.reply_as_admin = reply_as_admin

    def d(self):
        dict_ = super(YSComment, self).d()
        dict_.update(self.dictify('face', 'public', 'top', 'reply', 'reply_as_admin'))
        return dict_


class YSFile(YSIdNode):
    """永硕文件类"""

    def __init__(self, ftype, link, **kwargs):
        """
        :param ftype: 文件类型，即扩展名
        :param link: 文件下载链接
        """
        super(YSFile, self).__init__(type_=YSNodeType.FILE, **kwargs)
        self.ftype = ftype
        self.link = link

    def d(self):
        dict_ = super(YSFile, self).d()
        dict_.update(self.dictify('ftype', 'link'))
        return dict_


class YSText(YSIdNode):
    """永硕文字类"""

    def __init__(self, **kwargs):
        super(YSText, self).__init__(type_=YSNodeType.TEXT, **kwargs)


class YSLink(YSIdNode):
    """永硕链接类"""

    def __init__(self, link, **kwargs):
        super(YSLink, self).__init__(type_=YSNodeType.LINK, label=None, **kwargs)
        self.link = link

    def d(self):
        dict_ = super(YSLink, self).d()
        dict_.update(self.dictify('link'))
        return dict_


class YSQuerySet:
    """搜索集"""
    def __init__(self, children=None):
        self.children = children or []  # type: List[Union[YSMainFolder, YSFolder, YSLink, YSText, YSFile]]

    def search_children(self,
                        name=None,
                        label=None,
                        id_=None,
                        link=None,
                        types: Union[List[_Symbol], _Symbol, None] = None,
                        layers=1,
                        flatten=False) -> 'YSQuerySet':
        """
        搜索子资源
        :param flatten: 结构是否扁平化
        :param name: 名称
        :param label: 标签
        :param id_: ID
        :param link: 链接
        :param types: 可能的类型
        :param layers: 递归层数 0表示一直递归
        :return: 新的搜索集
        """
        if not types:
            types = [YSNodeType.FILE, YSNodeType.FOLDER, YSNodeType.LINK, YSNodeType.TEXT]
        if isinstance(types, _Symbol):
            types = [types]  # type: List[_Symbol]

        if layers < 0:
            layers = 1

        matched_set = []
        for child in self.children:
            child_name = getattr(child, 'name', None)
            child_label = getattr(child, 'label', None)
            child_id = getattr(child, 'id', None)
            child_link = getattr(child, 'link', None)
            child_ftype = getattr(child, 'type', None)
            if (name is None or (child_name and child_name.find(name) >= 0)) and \
                    (label is None or (child_label and child_label.find(label) >= 0)) and \
                    (id_ is None or child_id == id_) and \
                    (link is None or (child_link and child_link.find(link) >= 0)) and \
                    (child_ftype in types):
                matched_set.append(child)
            elif child_ftype == YSNodeType.FOLDER and (layers == 0 or layers > 1):
                matched_subset = child.search_children(name, label, id_, link, types, layers - 1, flatten)
                if flatten:
                    matched_set.extend(matched_subset.children)
                else:
                    child_ = copy.copy(child)
                    child_.children = matched_subset
                    matched_set.append(child_)

        return YSQuerySet(children=matched_set)

    def search_folders(self, name=None, label=None, id_=None, layers=1, flatten=False):
        return self.search_children(name, label, id_,
                                    types=YSNodeType.FOLDER, layers=layers, flatten=flatten)

    def search_unfolders(self, name=None, label=None, id_=None, link=None, layers=1, flatten=False):
        return self.search_children(name, label, id_, link,
                                    types=[YSNodeType.FILE, YSNodeType.TEXT, YSNodeType.LINK],
                                    layers=layers,
                                    flatten=flatten)

    def get_child(self, id_, type_: _Symbol, layers=0, flatten=False) -> Optional[YSNode]:
        matched_set = self.search_children(id_=id_, layers=layers, types=type_, flatten=flatten)
        if matched_set.children:
            return matched_set.children[0]
        return None


class YSFolder(YSNode, YSQuerySet):
    """永硕目录类"""

    def __init__(self, parent=None, **kwargs):
        super(YSFolder, self).__init__(type_=YSNodeType.FOLDER, **kwargs)
        self.children = []  # type: List[Union[YSMainFolder, YSFolder, YSLink, YSText, YSFile]]
        self.parent = parent  # type: YSMainFolder

    def _readable_children(self):
        return [child.d() for child in self.children]

    def d(self):
        dict_ = super(YSFolder, self).d()
        dict_.update(self.dictify('children'))
        return dict_

    def get_path(self):
        path = []
        folder = self  # type: Union[YSFolder, YSMainFolder]
        while not isinstance(folder, YSMainFolder):
            path.append(folder.name)
            folder = folder.parent
        path.reverse()
        return folder, '/'.join(path)


class YSAuthRights:
    def __init__(self, authed,
                 allow_list=None,
                 allow_upload=None,
                 allow_download=None,
                 allow_modify=None):
        self.authed = authed
        self.allow_list = allow_list
        self.allow_upload = allow_upload
        self.allow_download = allow_download
        self.allow_modify = allow_modify

    @staticmethod
    def b2c(b: bool):
        return ' ' if b is None else '01'[b]

    @staticmethod
    def c2b(c: str):
        return None if c == ' ' else bool(int(c))

    def from_string(self, rights):
        if self.authed:
            self.allow_list = True
            self.allow_modify = self.c2b(rights[0])
        else:
            self.allow_list = self.c2b(rights[0])
            self.allow_modify = False
        self.allow_upload = self.c2b(rights[1])
        self.allow_download = self.c2b(rights[2])
        return self

    def to_string(self):
        if self.authed:
            return '%s%s%s' % (
                self.b2c(self.allow_modify),
                self.b2c(self.allow_upload),
                self.b2c(self.allow_download))
        else:
            return '%s%s%s' % (
                self.b2c(self.allow_list),
                self.b2c(self.allow_upload),
                self.b2c(self.allow_download))

    def d(self):
        return self.to_string()

    def match(self, rights: 'YSAuthRights'):
        if self.allow_list is not None and self.allow_list != rights.allow_list:
            return False
        if self.allow_upload is not None and self.allow_upload != rights.allow_upload:
            return False
        if self.allow_download is not None and self.allow_download != rights.allow_download:
            return False
        if self.allow_modify is not None and self.allow_modify != rights.allow_modify:
            return False
        return True


class YSFolderRights:
    def __init__(self, client, rights: str = None):
        self.authed = self.unauthed = None  # type: Optional[YSAuthRights]
        self.client = client  # type: YSMainFolder
        self.reset(rights or ' ' * 6)

    def from_auth_rights(self, authed: YSAuthRights, unauthed: YSAuthRights):
        self.authed = authed
        self.unauthed = unauthed
        return self

    @property
    def allow_list(self):
        return self.client.core.author.ok or self.client.author.ok or self.unauthed.allow_list

    @property
    def allow_upload(self):
        return self.client.core.author.ok or \
               (self.client.author.ok and self.authed.allow_upload) or \
               (not self.client.author.ok and self.unauthed.allow_upload)

    @property
    def allow_download(self):
        return self.client.core.author.ok or \
               (self.client.author.ok and self.authed.allow_download) or \
               (not self.client.author.ok and self.unauthed.allow_download)

    @property
    def allow_modify(self):
        return self.client.core.author.ok or (self.client.author.ok and self.authed.allow_modify)

    def reset(self, rights: str):
        self.authed = YSAuthRights(True).from_string(rights)
        self.unauthed = YSAuthRights(False).from_string(rights[3:])

    def to_string(self):
        return '%s%s' % (self.authed.to_string(), self.unauthed.to_string())

    def match(self, rights: 'YSFolderRights'):
        return self.authed.match(rights.authed) and self.unauthed.match(rights.unauthed)


class YSMainFolder(YSFolder, YSIdNode):
    """永硕根目录类"""

    def __init__(self, **kwargs):
        super(YSMainFolder, self).__init__(**kwargs)

        self.rights = YSFolderRights(self)
        self.author = YSFolderLocker(client=self)  # 密钥验证装置

    def _readable_author(self):
        return self.author.d()

    def d(self):
        dict_ = super(YSMainFolder, self).d()
        dict_.update(self.dictify(
            'allow_list', 'allow_upload', 'allow_download', 'allow_modify', 'author'))
        return dict_

    def _fetch_rights_uri(self):
        return '{2}/f_ht/ajcx/mlrz.aspx?cz=Fhmlqx&mlbh={0}&_dlmc={1}&_dlmm={3}'.format(
            self.id, self.core.bucket, self.core.api_host, self.core.token)

    def fetch_rights(self):
        """获取根目录权限"""
        rights = self.core.sess.get(self._fetch_rights_uri(), decode=True)
        self.rights.reset(rights)
        return self

    @staticmethod
    def _recurrent_build_tree(parent: YSFolder, soup: Souper):
        # parent.children = []
        for child in soup.children:
            if not isinstance(child, bs4.Tag) or not child.name == 'li':
                continue

            class_ = child.get('class')[0]
            if class_ not in ['zml', 'gml', 'xwz', 'xlj', 'xwj']:
                continue

            if class_ == 'zml':
                name = child.find('a').text
                resource = YSFolder(parent=parent, name=name, label=None, core=parent.core)
                YSMainFolder._recurrent_build_tree(resource, soup.find('ul'))
            else:
                id_ = child.get('id')
                id_ = id_[id_.find('_') + 1:]

                if class_ == 'gml':
                    label = child.find('label').text
                    name = child.find('a').text
                    resource = YSMainFolder(name=name, label=label, core=parent.core, id_=id_)
                elif class_ == 'xwz':
                    name = child.find('b').text
                    label = child.find('i').text
                    resource = YSText(name=name, label=label, core=parent.core, id_=id_)
                elif class_ == 'xlj':
                    name = child.find('a').text
                    link = child.find('a').get('href')
                    resource = YSLink(name=name, link=link, core=parent.core, id_=id_)
                else:
                    name = child.find('a').text
                    link = child.find('a').get('data-url')
                    if not link:
                        link = child.find('a').get('href')
                    label = child.find('b').text
                    img = child.find('img').get('src')
                    ftype = img[img.rfind('/') + 1: img.rfind('.')]
                    resource = YSFile(name=name, label=label, core=parent.core, link=link,
                                      ftype=ftype, id_=id_)
            parent.children.append(resource)

    def _fetch_children_uri(self):
        return '{2}/f_ht/ajcx/wj.aspx?cz=dq&mlbh={0}&_dlmc={1}&_dlmm={3}'.format(
            self.id, self.core.bucket, self.core.api_host, self.core.token)

    def fetch_children(self):
        """获取子资源"""
        if not self.rights.allow_list:
            return self

        soup = self.core.sess.get(self._fetch_children_uri(), soup=True)  # type: Souper
        self.children = []
        self._recurrent_build_tree(self, soup)
        return self

    def auth(self, password):
        """验证密码"""
        if self.author.auth(password):
            self.fetch_rights()
        return self

    def fetch_file(self, file_id, parent: YSFolder):
        return self.core.fetch_file(file_id, parent)


class YS(YSMainFolder):
    api_host = 'http://cb.ys168.com'
    up_host = 'http://ys-j.ys168.com'

    """永硕类"""

    def __init__(self, bucket, password=None, entrance=None):
        """
        :param bucket: 永硕空间ID
        :param password: 管理员密码
        :param entrance: 空间进入密码
        """
        self.bucket = bucket

        self.sess = _Fetcher()
        self.friend_links = []  # type: List[YSFriendLink] # 友链
        self.comments = []  # type: List[YSComment]  # 留言板
        self.token = ''  # API访问密钥

        super(YS, self).__init__(label=None, id_=None, name=None, core=self)

        self.author = YSAdminLocker(client=self)  # 管理员认证器
        if password:
            self.author.auth(password)

        self.accessor = YSEntranceLocker(client=self)  # 访问认证器
        if entrance:
            self.accessor.auth(entrance)

        self._upload_file_count = 0
        self.root = self

    def reset(self):
        self.sess.reset()
        self.friend_links = []
        self.comments = []
        self.token = ''

        self.accessor.reset()
        self.author.reset()

        self.upload_file_count = 0

    @property
    def upload_file_count(self):
        self._upload_file_count += 1
        return self._upload_file_count - 1

    @upload_file_count.setter
    def upload_file_count(self, v):
        self._upload_file_count = v

    @property
    def host(self):
        return 'http://{0}.ys168.com'.format(self.bucket)

    def fetch_rights(self):
        raise NotImplementedError

    def _fetch_children_uri(self):
        return '{1}/f_ht/ajcx/ml.aspx?cz=ml_dq&_dlmc={0}&_dlmm={2}'.format(
            self.bucket, self.api_host, self.token)

    def fetch_children(self):
        if not self.accessor.ok:
            return self

        soup = self.sess.get(self._fetch_children_uri(), soup=True)  # type: Souper
        self.children = []
        self._recurrent_build_tree(self, soup)
        return self

    def fetch_info(self):
        """获取主页名称和友链信息"""
        if not self.accessor.ok:
            return self
        soup = self.sess.get(self.host, soup=True)  # type: Souper

        self.name = soup.find(id='kjbt').text
        self.friend_links = [YSFriendLink(
            name=link.text, link=link.get('href')) for link in soup.find(id='sylj')('a')]
        return self

    def _fetch_comments_uri(self):
        return '{1}/f_ht/ajcx/lyd.aspx?cz=lyxs&n=1&dqy=0&lybh=0&zts=0&_dlmc={0}&_dlmm={2}'.format(
            self.bucket, self.api_host, self.token)

    def fetch_comments(self):
        """获取主页留言板信息"""
        if not self.accessor.ok:
            return self
        soup = self.sess.get(self._fetch_comments_uri(), soup=True)  # type: Souper

        self.comments = []
        for comment in soup(class_='lyk'):
            id_ = comment.get('id')[1:]
            params = comment.get('data-pd')
            face = int(params[0])
            public = params[1] == '1'
            top = params[2] == '1'
            reply_as_admin = params[3] == '1'
            name = comment.find(class_='lysm').text
            label = comment.find(class_='lynr').find('div').get_text('\n')
            reply = comment.find(class_='lyhf')
            if reply:
                reply = reply.find('div').get_text('\n')
            self.comments.append(YSComment(
                face=face, public=public, top=top, reply=reply, reply_as_admin=reply_as_admin,
                name=name, label=label, id_=id_, core=self))
        return self

    def fetch_tree(self):
        """获取整个资源树"""
        self.fetch_children()
        for child in self.children:
            child.fetch_children()
        return self

    def _readable_friend_links(self):
        return [friend_link.d() for friend_link in self.friend_links]

    def _readable_comments(self):
        return [comment.d() for comment in self.comments]

    def _readable_accessor(self):
        return self.accessor.d()

    def d(self):
        dict_ = super(YSMainFolder, self).d()
        dict_.update(self.dictify('friend_links', 'comments', 'accessor'))
        return dict_

    def _add_folder_uri(self, folder: YSMainFolder):
        return '{0}/f_ht/ajcx/ml.aspx?cz=Ml_add&qx={1}&_dlmc={2}&_dlmm={3}'.format(
            self.api_host, folder.rights.to_string(), self.bucket, self.token)

    def search_folders(self, rights: Union[str, YSFolderRights] = None, **kwargs) -> YSQuerySet:
        if not rights:
            rights = ' ' * 6
        if isinstance(rights, str):
            rights = YSFolderRights(None, rights)

        middle_set = super(YS, self).search_folders(**kwargs, layers=1)
        matched_set = []
        for child in middle_set.children:
            if isinstance(child, YSMainFolder) and rights.match(child.rights):
                matched_set.append(child)

        return YSQuerySet(children=matched_set)

    def get_folder(self, id_) -> Optional[YSMainFolder]:
        return self.get_child(id_, type_=YSNodeType.FOLDER, layers=1)

    def add_folder(self, folder: YSMainFolder):
        if not self.author.ok:
            return

        folder.id = self.sess.post(self._add_folder_uri(folder), dict(
            bt=folder.name,
            sm=folder.label,
            kqmm=folder.author.password or ''
        ))

        self.children.append(folder)
        return self

    def _modify_folder_uri(self, folder: YSMainFolder):
        return '{0}/f_ht/ajcx/ml.aspx?cz=Ml_bj&qx={1}&mlbh={2}&_dlmc={3}&_dlmm={4}'.format(
            self.api_host, folder.rights.to_string(), folder.id, self.bucket, self.token)

    def modify_folder(self, folder: YSMainFolder):
        if not self.author.ok:
            return

        self.sess.post(self._modify_folder_uri(folder), dict(
            bt=folder.name,
            sm=folder.label,
            kqmm=folder.author.password or ''
        ))
        return self

    def _delete_folder_uri(self, folder: YSMainFolder):
        return '{0}/f_ht/ajcx/ml.aspx?cz=Ml_del&mlbh={1}&_dlmc={2}&_dlmm={3}'.format(
            self.api_host, folder.id, self.bucket, self.token)

    def delete_folder(self, folder: Union[YSMainFolder, str]):
        """
        :param folder: 主目录或主目录ID
        """
        if not self.author.ok:
            return

        if isinstance(folder, str):
            folder = self.get_folder(folder)
        if not folder:
            return

        self.sess.get(self._delete_folder_uri(folder))
        self.children.remove(folder)
        return self

    def _fetch_upload_token_uri(self, folder: YSMainFolder):
        return '{0}/f_ht/ajcx/wj.aspx?cz=dq&mlbh={1}&_dlmc={2}&_dlmm={3}'.format(
            self.api_host, folder.id, self.bucket, self.token)

    def fetch_upload_token(self, folder: YSMainFolder):
        data = self.sess.get(self._fetch_upload_token_uri(folder), decode=True)
        matcher = re.search("scpz = '(.*?)'", data)
        return matcher.group(1) if matcher else None

    def _fetch_file_uri(self, file_id, folder: YSMainFolder):
        return '{0}/f_ht/ajcx/wj.aspx?cz=Dqfile&wjbh={1}&mlbh={2}&_dlmc={3}&_dlmm={4}'.format(
            self.api_host, file_id, folder.id, self.bucket, self.token)

    def fetch_file(self, file_id, parent: YSFolder):
        root, _ = parent.get_path()
        soup = self.sess.get(self._fetch_file_uri(file_id, root), soup=True)
        self._recurrent_build_tree(parent, soup)
        return self

    def _fetch_upload_uri(self, web_path, filename, label):
        return '{0}/fileup/js.aspx?zml={1}&wjm={2}&wjbz={3}'.format(
            self.up_host, web_path, filename, label or '')

    def upload_file(self, folder: Union[YSFolder, str], filepath, label=None):
        if not self.author.ok:
            return

        if isinstance(folder, str):
            folder = self.get_folder(folder)
        parent = folder

        if not isinstance(folder, YSMainFolder):
            web_path, folder = folder.get_path()
        else:
            web_path = ''

        if not folder:
            return

        mime, _ = mimetypes.guess_type(filepath)
        upload_token = self.fetch_upload_token(folder)
        files = dict(file=(os.path.basename(filepath), open(filepath, 'rb'), mime))
        filename = os.path.basename(filepath)

        file_id = self.sess.post(
            url=self._fetch_upload_uri(web_path, filename, label),
            data=dict(pz=upload_token),
            files=files,
            jsonify=True,
        )['wjbh']

        self.fetch_file(file_id, parent)
        return self
