import copy
from typing import Union, List, Optional

from bs4 import BeautifulSoup as Souper

from .base import _Symbol, _Dictifier


class YSNodeType:
    """永硕节点类型"""
    FILE = _Symbol()
    FOLDER = _Symbol()
    TEXT = _Symbol()
    LINK = _Symbol()
    # COMMENT = _Symbol()


class YSPath(_Dictifier):
    def __init__(self, path):
        from .node import YSMainFolder
        self.path = path  # type: List[YSNode, YSMainFolder]

    @property
    def root(self):
        return self.path[0]

    def get_string(self, with_root=False):
        start = int(not with_root)
        return '/'.join(list(map(lambda node: node.name, self.path[start:])))


class YSNode(_Dictifier):
    """永硕基本节点"""

    def __init__(self, parent, name, type_: _Symbol, core, label=None):
        """
        节点构造器
        :param name: 节点名称
        :param type_: 节点类型，应为YSNodeType的其中一类
        :param label: 节点标签
        :param core: 节点所属的永硕网盘类
        """
        self.name = name
        self.type = type_
        self.label = label or ''

        from .node import YS, YSFolder
        self.core = core  # type: YS
        self.parent = parent  # type: YSFolder

    def __str__(self):
        return self.name

    def _readable_type(self):
        for key in YSNodeType.__dict__:
            type_ = getattr(YSNodeType, key, None)
            if self.type == type_:
                return key
        return self.type

    def get_path(self):
        path_ = []
        node = self  # type: Union[YSNode]

        from .node import YSMainFolder
        while not isinstance(node, YSMainFolder):
            path_.append(node)
            node = node.parent
        path_.append(node)
        path_.reverse()
        return YSPath(path_)

    def d(self):
        return self.dictify('name', 'type', 'label')


class YSIdNode(YSNode):
    """含有ID的永硕基本节点"""

    def __init__(self, id_=None, **kwargs):
        super(YSIdNode, self).__init__(**kwargs)
        self._id = id_

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, id_):
        if self._id is None:
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


class YSComment(_Dictifier):
    """永硕留言类"""

    def __init__(self, face, public, top, reply, reply_as_admin, id_, name, content, core):
        """
        :param face: 留言表情
        :param public: 是否公开
        :param top: 是否置顶
        :param reply: 回复内容
        :param reply_as_admin: 是否以管理员身份回复
        """
        self.face = face
        self.public = public
        self.top = top
        self.reply = reply
        self.reply_as_admin = reply_as_admin
        self.id = id_
        self.name = name
        self.content = content

        from .node import YS
        self.core = core  # type: YS

    def d(self):
        # dict_ = super(YSComment, self).d()
        return self.dictify(
            'face', 'public', 'top', 'reply', 'reply_as_admin', 'id', 'name', 'content')


class YSZoneInfo(_Dictifier):
    def __init__(self, client):
        from .node import YS
        self.client = client  # type: YS

        self.friend_links = []  # type: List[YSFriendLink] # 友链
        self.comments = []  # type: List[YSComment]  # 留言板

    def fetch_info(self):
        """获取主页名称和友链信息"""
        if not self.client.accessor.ok:
            return self
        soup = self.client.sess.get(self.client.host, soup=True)  # type: Souper

        self.client.name = soup.find(id='kjbt').text
        self.friend_links = [YSFriendLink(
            name=link.text, link=link.get('href')) for link in soup.find(id='sylj')('a')]
        return self

    def _fetch_comments_uri(self):
        return '{1}/f_ht/ajcx/lyd.aspx?cz=lyxs&n=1&dqy=0&lybh=0&zts=0&_dlmc={0}&_dlmm={2}'.format(
            self.client.bucket, self.client.api_host, self.client.token)

    def fetch_comments(self):
        """获取主页留言板信息"""
        if not self.client.accessor.ok:
            return self
        soup = self.client.sess.get(self._fetch_comments_uri(), soup=True)  # type: Souper

        self.comments = []
        for comment in soup(class_='lyk'):
            id_ = comment.get('id')[1:]
            params = comment.get('data-pd')
            face = int(params[0])
            public = params[1] == '1'
            top = params[2] == '1'
            reply_as_admin = params[3] == '1'
            name = comment.find(class_='lysm').text
            content = comment.find(class_='lynr').find('div').get_text('\n')
            reply = comment.find(class_='lyhf')
            if reply:
                reply = reply.find('div').get_text('\n')
            self.comments.append(YSComment(
                face=face, public=public, top=top, reply=reply, reply_as_admin=reply_as_admin,
                name=name, content=content, id_=id_, core=self))
        return self

    def reset(self):
        self.fetch_info()
        self.fetch_comments()

    def _readable_friend_links(self):
        return [friend_link.d() for friend_link in self.friend_links]

    def _readable_comments(self):
        return [comment.d() for comment in self.comments]

    def d(self):
        return self.dictify('friend_links', 'comments')


class YSQuerySet:
    """搜索集"""

    def __init__(self, nodes=None):
        from .node import YSMainFolder, YSFolder, YSLink, YSText, YSFile
        self.nodes = nodes or []  # type: List[Union[YSMainFolder, YSFolder, YSLink, YSText, YSFile]]

    def search_nodes(self,
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
        for node in self.nodes:
            node_name = getattr(node, 'name', None)
            node_label = getattr(node, 'label', None)
            node_id = getattr(node, 'id', None)
            node_link = getattr(node, 'link', None)
            node_ftype = getattr(node, 'type', None)
            if (name is None or (node_name and node_name.find(name) >= 0)) and \
                    (label is None or (node_label and node_label.find(label) >= 0)) and \
                    (id_ is None or node_id == id_) and \
                    (link is None or (node_link and node_link.find(link) >= 0)) and \
                    (node_ftype in types):
                matched_set.append(node)
            elif node_ftype == YSNodeType.FOLDER and (layers == 0 or layers > 1):
                matched_subset = node.search_nodes(name, label, id_, link, types, layers - 1,
                                                   flatten)
                if flatten:
                    matched_set.extend(matched_subset.nodes)
                else:
                    node_ = copy.copy(node)
                    node_.nodes = matched_subset
                    matched_set.append(node_)

        return YSQuerySet(nodes=matched_set)

    def search_folders(self, name=None, label=None, id_=None, layers=1, flatten=False):
        return self.search_nodes(name, label, id_,
                                 types=YSNodeType.FOLDER, layers=layers, flatten=flatten)

    def search_unfolders(self, name=None, label=None, id_=None, link=None, layers=1, flatten=False):
        return self.search_nodes(name, label, id_, link,
                                 types=[YSNodeType.FILE, YSNodeType.TEXT, YSNodeType.LINK],
                                 layers=layers,
                                 flatten=flatten)

    def get_node(self, id_, type_: _Symbol, layers=0, flatten=False) -> Optional[YSNode]:
        matched_set = self.search_nodes(id_=id_, layers=layers, types=type_, flatten=flatten)
        if not matched_set.empty:
            return matched_set.nodes[0]
        return None

    @property
    def empty(self):
        return len(self.nodes) == 0
