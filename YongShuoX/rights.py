from typing import Optional


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

        from .node import YSMainFolder
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
