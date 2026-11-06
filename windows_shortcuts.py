"""Small Windows Shell Link wrapper; no external shell or scripting host."""
import ctypes
from ctypes import wintypes
import uuid


class GUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check(result):
    if result < 0:
        raise OSError(f'Windows Shell Link HRESULT 0x{result & 0xffffffff:08x}')


class ShellLink:
    def __enter__(self):
        self.pointer = ctypes.c_void_p()
        self.persist = ctypes.c_void_p()
        self.ole = ctypes.OleDLL('ole32')
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.ole.CoInitializeEx.restype = ctypes.c_long
        result = self.ole.CoInitializeEx(None, 2)
        self.initialized = result >= 0
        if result < 0 and result & 0xffffffff != 0x80010106:
            _check(result)
        try:
            self.ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p,
                                                  wintypes.DWORD, ctypes.POINTER(GUID),
                                                  ctypes.POINTER(ctypes.c_void_p)]
            self.ole.CoCreateInstance.restype = ctypes.c_long
            _check(self.ole.CoCreateInstance(
                ctypes.byref(GUID.parse('00021401-0000-0000-c000-000000000046')), None, 1,
                ctypes.byref(GUID.parse('000214f9-0000-0000-c000-000000000046')),
                ctypes.byref(self.pointer)))
            self.call(self.pointer, 0, [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                      ctypes.byref(GUID.parse('0000010b-0000-0000-c000-000000000046')),
                      ctypes.byref(self.persist))
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    @staticmethod
    def call(pointer, index, types, *args):
        address = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
        function = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(address)
        result = function(pointer, *args)
        if index != 2:
            _check(result)
        return result

    def __exit__(self, *args):
        for pointer in (self.persist, self.pointer):
            if pointer.value:
                self.call(pointer, 2, [])
                pointer.value = None
        if self.initialized:
            self.ole.CoUninitialize()

    def text(self, index, path=False):
        buffer = ctypes.create_unicode_buffer(32768)
        types = [wintypes.LPWSTR, ctypes.c_int]
        args = [buffer, len(buffer)]
        if path:
            types += [ctypes.c_void_p, wintypes.DWORD]
            args += [None, 0]
        self.call(self.pointer, index, types, *args)
        return buffer.value


def read_shortcut(path):
    with ShellLink() as link:
        link.call(link.persist, 5, [wintypes.LPCWSTR, wintypes.DWORD], str(path), 0)
        return dict(target=link.text(3, path=True), arguments=link.text(10), directory=link.text(8))


def write_shortcut(path, target, arguments, directory):
    with ShellLink() as link:
        for index, value in ((20, target), (11, arguments), (9, directory), (7, 'Epic7 Assist Bot')):
            link.call(link.pointer, index, [wintypes.LPCWSTR], str(value))
        link.call(link.pointer, 17, [wintypes.LPCWSTR, ctypes.c_int], str(target), 0)
        link.call(link.persist, 6, [wintypes.LPCWSTR, wintypes.BOOL], str(path), True)


def desktop_folder():
    shell = ctypes.OleDLL('shell32')
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                         wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    pointer = ctypes.c_void_p()
    _check(shell.SHGetKnownFolderPath(ctypes.byref(GUID.parse(
        'b4bfcc3a-db2c-424c-b029-7fe99a87c641')), 0, None, ctypes.byref(pointer)))
    try:
        return ctypes.wstring_at(pointer)
    finally:
        ole = ctypes.OleDLL('ole32')
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole.CoTaskMemFree(pointer)
