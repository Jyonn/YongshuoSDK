import mimetypes
import os
import re
from typing import List, Union, Optional

import bs4
from bs4 import BeautifulSoup as Souper
from smartify import E

from .rights import YSFolderRights
from .modules import YSIdNode, YSNodeType, YSNode, YSQuerySet, YSZoneInfo
from .base import Fetcher, YSError
from .locker import YSFolderLocker, YSAdminLocker, YSEntranceLocker


@E.register()
class NodeError:
    NOT_AUTHOR = E("需要管理员权限")
    INACCESSIBLE = E("需要访问密码")


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

    def _upload_uri(self, web_path, filename, label):
        return '{0}/fileup/js.aspx?zml={1}&wjm={2}&wjbz={3}'.format(
            self.core.up_host, web_path, filename, label or '')

    def upload(self, filepath, label=None):
        path = self.get_path()
        root = path.root  # type: YSMainFolder
        if not root.author.ok:
            raise NodeError.NOT_AUTHOR

        mime, _ = mimetypes.guess_type(filepath)
        upload_token = self.core.fetch_upload_token()
        files = dict(file=(os.path.basename(filepath), open(filepath, 'rb'), mime))
        filename = os.path.basename(filepath)

        file_id = self.core.sess.post(
            url=self._upload_uri(path.get_string(), filename, label),
            data=dict(pz=upload_token),
            files=files,
            jsonify=True,
        )['wjbh']

        self.core.fetch_file(file_id, root)
        return self


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


class YSFolder(YSNode, YSQuerySet):
    """永硕目录类"""

    def __init__(self, **kwargs):
        super(YSFolder, self).__init__(type_=YSNodeType.FOLDER, **kwargs)
        self.nodes = []  # type: List[Union[YSMainFolder, YSFolder, YSLink, YSText, YSFile]]

    def _readable_nodes(self):
        return [node.d() for node in self.nodes]

    def d(self):
        dict_ = super(YSFolder, self).d()
        dict_.update(self.dictify('nodes'))
        return dict_

    def add_folder(self, folder: 'YSFolder'):
        self.nodes.append(folder)


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
        for child in soup.children:
            if not isinstance(child, bs4.Tag) or not child.name == 'li':
                continue

            class_ = child.get('class')[0]
            if class_ not in ['zml', 'gml', 'xwz', 'xlj', 'xwj']:
                continue

            exist = False

            if class_ == 'zml':
                name = child.find('a').text
                query_set = parent.search_nodes(name=name)
                if query_set.empty:
                    resource = YSFolder(parent=parent, name=name, label=None, core=parent.core)
                else:
                    resource = query_set.nodes[0]
                    exist = True
                YSMainFolder._recurrent_build_tree(resource, soup.find('ul'))
            else:
                id_ = child.get('id')
                id_ = id_[id_.find('_') + 1:]

                if class_ == 'gml':
                    label = child.find('label').text
                    name = child.find('a').text
                    resource = parent.get_node(id_=id_, type_=YSNodeType.FOLDER)
                    if not resource:
                        resource = YSMainFolder(name=name, label=label, core=parent.core, id_=id_)
                    else:
                        exist = True
                elif class_ == 'xwz':
                    name = child.find('b').text
                    label = child.find('i').text
                    resource = parent.get_node(id_=id_, type_=YSNodeType.TEXT)
                    if not resource:
                        resource = YSText(name=name, label=label, core=parent.core, id_=id_)
                    else:
                        exist = True
                elif class_ == 'xlj':
                    name = child.find('a').text
                    link = child.find('a').get('href')
                    resource = parent.get_node(id_=id_, type_=YSNodeType.LINK)
                    if not resource:
                        resource = YSLink(name=name, link=link, core=parent.core, id_=id_)
                    else:
                        exist = True
                else:
                    name = child.find('a').text
                    link = child.find('a').get('data-url')
                    if not link:
                        link = child.find('a').get('href')
                    label = child.find('b').text
                    img = child.find('img').get('src')
                    ftype = img[img.rfind('/') + 1: img.rfind('.')]
                    resource = parent.get_node(id_=id_, type_=YSNodeType.FILE)
                    if not resource:
                        resource = YSFile(name=name, label=label, core=parent.core, link=link,
                                          ftype=ftype, id_=id_)
                    else:
                        exist = True
            if not exist:
                parent.nodes.append(resource)

    def _fetch_nodes_uri(self):
        return '{2}/f_ht/ajcx/wj.aspx?cz=dq&mlbh={0}&_dlmc={1}&_dlmm={3}'.format(
            self.id, self.core.bucket, self.core.api_host, self.core.token)

    def fetch_nodes(self):
        """获取子资源"""
        if not self.rights.allow_list:
            return self

        soup = self.core.sess.get(self._fetch_nodes_uri(), soup=True)  # type: Souper
        self.nodes = []
        self._recurrent_build_tree(self, soup)
        return self

    def auth(self, password):
        """验证密码"""
        if self.author.auth(password):
            self.fetch_rights()
        return self

    def _fetch_file_uri(self, file_id):
        return '{0}/f_ht/ajcx/wj.aspx?cz=Dqfile&wjbh={1}&mlbh={2}&_dlmc={3}&_dlmm={4}'.format(
            self.core.api_host, file_id, self.id, self.core.bucket, self.core.token)

    def fetch_file(self, file_id):
        soup = self.core.sess.get(self._fetch_file_uri(file_id), soup=True)
        self._recurrent_build_tree(self, soup)
        return self

    def _modify_uri(self):
        return '{0}/f_ht/ajcx/ml.aspx?cz=Ml_bj&qx={1}&mlbh={2}&_dlmc={3}&_dlmm={4}'.format(
            self.core.api_host, self.rights.to_string(), self.id, self.core.bucket, self.core.token)

    def modify(self, name, label, password):
        if not self.core.author.ok:
            raise NodeError.NOT_AUTHOR

        self.name = name
        self.label = label
        self.author.password = password

        self.core.sess.post(self._modify_uri(), dict(
            bt=self.name,
            sm=self.label,
            kqmm=self.author.password
        ))
        return self

    def _add_uri(self):
        return '{0}/f_ht/ajcx/ml.aspx?cz=Ml_add&qx={1}&_dlmc={2}&_dlmm={3}'.format(
            self.core.api_host, self.rights.to_string(), self.core.bucket, self.core.token)

    def add(self):
        if not self.core.author.ok:
            return

        self.id = self.core.sess.post(self._add_uri(), dict(
            bt=self.name,
            sm=self.label,
            kqmm=self.author.password
        ))

        self.parent.nodes.append(self)
        return self

    def _delete_uri(self):
        return '{0}/f_ht/ajcx/ml.aspx?cz=Ml_del&mlbh={1}&_dlmc={2}&_dlmm={3}'.format(
            self.core.api_host, self.id, self.core.bucket, self.core.token)

    def delete(self):
        if not self.core.author.ok:
            raise NodeError.NOT_AUTHOR

        self.core.sess.get(self._delete_uri())
        self.parent.nodes.remove(self)

    def _upload_token_uri(self):
        return '{0}/f_ht/ajcx/wj.aspx?cz=dq&mlbh={1}&_dlmc={2}&_dlmm={3}'.format(
            self.core.api_host, self.id, self.core.bucket, self.core.token)

    def upload_token(self):
        data = self.core.sess.get(self._upload_token_uri(), decode=True)
        matcher = re.search("scpz = '(.*?)'", data)
        return matcher.group(1) if matcher else None


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

        self.sess = Fetcher()
        self.token = ''  # API访问口令
        self.info = YSZoneInfo(client=self)

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
        self.token = ''

        self.accessor.reset()
        self.author.reset()
        self.info.reset()

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
        raise YSError.NOT_IMPLEMENTED

    def _fetch_nodes_uri(self):
        return '{1}/f_ht/ajcx/ml.aspx?cz=ml_dq&_dlmc={0}&_dlmm={2}'.format(
            self.bucket, self.api_host, self.token)

    def fetch_nodes(self):
        if not self.accessor.ok:
            raise NodeError.INACCESSIBLE

        soup = self.sess.get(self._fetch_nodes_uri(), soup=True)  # type: Souper
        self.nodes = []
        self._recurrent_build_tree(self, soup)
        return self

    def fetch_tree(self):
        """获取整个资源树"""
        self.fetch_nodes()
        for node in self.nodes:
            node.fetch_nodes()
        return self

    def _readable_info(self):
        return self.info.d()

    def _readable_accessor(self):
        return self.accessor.d()

    def d(self):
        dict_ = super(YSMainFolder, self).d()
        dict_.update(self.dictify('info', 'accessor'))
        return dict_

    def search_folders(self, rights: Union[str, YSFolderRights] = None, **kwargs) -> YSQuerySet:
        if not rights:
            rights = ' ' * 6
        if isinstance(rights, str):
            rights = YSFolderRights(None, rights)

        middle_set = super(YS, self).search_folders(**kwargs, layers=1)
        matched_set = []
        for node in middle_set.nodes:
            if isinstance(node, YSMainFolder) and rights.match(node.rights):
                matched_set.append(node)

        return YSQuerySet(nodes=matched_set)

    def get_folder(self, id_) -> Optional[YSMainFolder]:
        return self.get_node(id_, type_=YSNodeType.FOLDER, layers=1)
