from __future__ import print_function, division, absolute_import

import hashlib
import logging
import os
import re
import sys
import tempfile
import warnings
from collections import Hashable
from functools import partial, wraps
from inspect import isbuiltin
from os.path import abspath, isdir
from types import GeneratorType

import psutil

__all__ = ['can_open', 'can_open_all', 'can_open_all_files_in_prefix',
           'try_write', 'hashsum_file', 'md5_file', 'url_path',
           'win_path_to_unix', 'unix_path_to_win', 'win_path_to_cygwin',
           'cygwin_path_to_win', 'translate_stream', 'human_bytes',
           'memoized', 'memoize', 'find_parent_shell', 'deprecated',
           'deprecated_import', 'import_and_wrap_deprecated']

log = logging.getLogger(__name__)
stderrlog = logging.getLogger('stderrlog')


def can_open(file):
    """
    Return True if the given ``file`` can be opened for writing
    """
    try:
        fp = open(file, "ab")
        fp.close()
        return True
    except IOError:
        stderrlog.info("Unable to open %s\n" % file)
        return False


def can_open_all(files):
    """
    Return True if all of the provided ``files`` can be opened
    """
    for f in files:
        if not can_open(f):
            return False
    return True


def can_open_all_files_in_prefix(prefix, files):
    """
    Returns True if all ``files`` at a given ``prefix`` can be opened
    """
    return can_open_all((os.path.join(prefix, f) for f in files))

def try_write(dir_path):
    assert isdir(dir_path)
    try:
        with tempfile.TemporaryFile(prefix='.conda-try-write',
                                    dir=dir_path) as fo:
            fo.write(b'This is a test file.\n')
        return True
    except (IOError, OSError):
        return False


def hashsum_file(path, mode='md5'):
    h = hashlib.new(mode)
    with open(path, 'rb') as fi:
        while True:
            chunk = fi.read(262144)  # process chunks of 256KB
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def md5_file(path):
    return hashsum_file(path, 'md5')


def url_path(path):
    path = abspath(path)
    if sys.platform == 'win32':
        path = '/' + path.replace(':', '|').replace('\\', '/')
    return 'file://%s' % path


def win_path_to_unix(path, root_prefix=""):
    """Convert a path or ;-separated string of paths into a unix representation

    Does not add cygdrive.  If you need that, set root_prefix to "/cygdrive"
    """
    path_re = '(?<![:/])([a-zA-Z]:[\/\\\\]+(?:[^:*?"<>|]+[\/\\\\]+)*[^:*?"<>|;\/\\\\]+?(?![a-zA-Z]:))'
    translation = lambda found_path: root_prefix + "/" + found_path.groups()[0].replace("\\", "/")\
        .replace(":", "").replace(";", ":")
    return re.sub(path_re, translation, path)


def unix_path_to_win(path, root_prefix=""):
    """Convert a path or :-separated string of paths into a Windows representation

    Does not add cygdrive.  If you need that, set root_prefix to "/cygdrive"
    """
    if len(path) > 1 and (";" in path or (path[1] == ":" and path.count(":") == 1)):
        # already a windows path
        return path.replace("/", "\\")
    """Convert a path or :-separated string of paths into a Windows representation"""
    path_re = root_prefix +'(/[a-zA-Z]\/(?:[^:*?"<>|]+\/)*[^:*?"<>|;]*)'
    translation = lambda found_path: found_path.group(0)[len(root_prefix)+1] + ":" + \
                  found_path.group(0)[len(root_prefix)+2:].replace("/", "\\")
    translation = re.sub(path_re, translation, path)
    translation = re.sub(":([a-zA-Z]):", lambda match: ";" + match.group(0)[1] + ":", translation)
    return translation


# curry cygwin functions
win_path_to_cygwin = lambda path : win_path_to_unix(path, "/cygdrive")
cygwin_path_to_win = lambda path : unix_path_to_win(path, "/cygdrive")


def translate_stream(stream, translator):
    return "\n".join([translator(line) for line in stream.split("\n")])


def human_bytes(n):
    """
    Return the number of bytes n in more human readable form.
    """
    if n < 1024:
        return '%d B' % n
    k = n/1024
    if k < 1024:
        return '%d KB' % round(k)
    m = k/1024
    if m < 1024:
        return '%.1f MB' % m
    g = m/1024
    return '%.2f GB' % g


# class memoized(object):
#     """Decorator. Caches a function's return value each time it is called.
#     If called later with the same arguments, the cached value is returned
#     (not reevaluated).
#     """
#     def __init__(self, func):
#         self.func = func
#         self.cache = {}
#     def __call__(self, *args, **kw):
#         newargs = []
#         for arg in args:
#             if isinstance(arg, list):
#                 newargs.append(tuple(arg))
#             elif not isinstance(arg, collections.Hashable):
#                 # uncacheable. a list, for instance.
#                 # better to not cache than blow up.
#                 return self.func(*args, **kw)
#             else:
#                 newargs.append(arg)
#         newargs = tuple(newargs)
#         key = (newargs, frozenset(kw.items()))
#         if key in self.cache:
#             return self.cache[key]
#         else:
#             value = self.func(*args, **kw)
#             self.cache[key] = value
#             return value
def memoized(func):
    """
    Decorator to cause a function to cache it's results for each combination of
    inputs and return the cached result on subsequent calls.  Does not support
    named arguments or arg values that are not hashable.

    >>> @memoized
    ... def foo(x):
    ...     print('running function with', x)
    ...     return x+3
    ...
    >>> foo(10)
    running function with 10
    13
    >>> foo(10)
    13
    >>> foo(11)
    running function with 11
    14
    >>> @memoized
    ... def range_tuple(limit):
    ...     print('running function')
    ...     return tuple(i for i in range(limit))
    ...
    >>> range_tuple(3)
    running function
    (0, 1, 2)
    >>> range_tuple(3)
    (0, 1, 2)
    >>> @memoize
    ... def range_iter(limit):
    ...     print('running function')
    ...     return (i for i in range(limit))
    ...
    >>> range_iter(3)
    Traceback (most recent call last):
    TypeError: Can't memoize a generator!
    """
    func._result_cache = {}  # pylint: disable-msg=W0212

    @wraps(func)
    def _memoized_func(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key in func._result_cache:  # pylint: disable-msg=W0212
            return func._result_cache[key]  # pylint: disable-msg=W0212
        else:
            result = func(*args, **kwargs)
            if isinstance(result, GeneratorType) or isinstance(result, Hashable):
                # cannot be memoized; better not to cache than blowup
                return result
            func._result_cache[key] = result  # pylint: disable-msg=W0212
            return result

    return _memoized_func


# For instance methods only
class memoize(object): # 577452
    def __init__(self, func):
        self.func = func
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self.func
        return partial(self, obj)
    def __call__(self, *args, **kw):
        obj = args[0]
        try:
            cache = obj.__cache
        except AttributeError:
            cache = obj.__cache = {}
        key = (self.func, args[1:], frozenset(kw.items()))
        try:
            res = cache[key]
        except KeyError:
            res = cache[key] = self.func(*args, **kw)
        return res


def find_parent_shell(path=False):
    """return process name or path of parent.  Default is to return only name of process."""
    process = psutil.Process()
    while "conda" in process.parent().name():
        process = process.parent()
    if path:
        return process.parent().exe()
    return process.parent().name()


def deprecated(func):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emmitted
    when the function is used."""
    if callable(func):
        def new_func(*args, **kwargs):
            warnings.simplefilter('always', DeprecationWarning)  # turn off filter
            warnings.warn("Call to deprecated {0}.".format(func.__name__),
                          category=DeprecationWarning,
                          stacklevel=2)
            warnings.simplefilter('default', DeprecationWarning)  # reset filter
            return func(*args, **kwargs)
        new_func.__name__ = func.__name__
        new_func.__doc__ = func.__doc__
        new_func.__dict__.update(func.__dict__)
    else:
        raise NotImplementedError()
    return new_func


def deprecated_import(module_name):
    warnings.simplefilter('always', ImportWarning)  # turn off filter
    warnings.warn("Import of deprecated module {0}.".format(module_name),
                  category=ImportWarning)
    warnings.simplefilter('default', ImportWarning)  # reset filter


def import_and_wrap_deprecated(module_name, module_dict, warn_import=True):
    if warn_import:
        deprecated_import(module_name)

    from importlib import import_module
    module = import_module(module_name)
    for attr in module.__all__:
        module_dict[attr] = deprecated(getattr(module, attr))


def deprecate_module_with_proxy(module_name, module_dict, deprecated_attributes=None):
    def _ModuleProxy(module, depr):
        """Return a wrapped object that warns about deprecated accesses"""
        # http://stackoverflow.com/a/922693/2127762
        class Wrapper(object):
            def __getattr__(self, attr):
                if depr is None or attr in depr:
                    warnings.warn("Property %s is deprecated" % attr)

                return getattr(module, attr)

            def __setattr__(self, attr, value):
                if depr is None or attr in depr:
                    warnings.warn("Property %s is deprecated" % attr)
                return setattr(module, attr, value)
        return Wrapper()

    deprecated_import(module_name)

    deprs = set()
    for key in deprecated_attributes or module_dict:
        if key.startswith('_'):
            continue
        if callable(module_dict[key]) and not isbuiltin(module_dict[key]):
            module_dict[key] = deprecated(module_dict[key])
        else:
            deprs.add(key)
    sys.modules[module_name] = _ModuleProxy(sys.modules[module_name], deprs or None)