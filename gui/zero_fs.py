# zero/gui/zero_fs.py

import os
import sys
import errno
from fuse import FUSE, Operations, LoggingMixIn

class ZeroFS(LoggingMixIn, Operations):
    """
    A virtual filesystem that exposes Zero's state as a directory tree.
    """
    def __init__(self):
        # Initial state representation
        self.files = {
            '/status': b'idle\n',
            '/intent': b'no current intent\n',
            '/context': b'no context captured\n',
        }

    def getattr(self, path, fh=None):
        print(f"DEBUG: getattr called for {path}")
        if path == '/':
            return {'st_mode': (0o40755), 'st_size': 4096}
        if path in self.files:
            return {'st_mode': (0o100644), 'st_size': len(self.files[path]), 'st_uid': os.getuid(), 'st_gid': os.getgid()}
        raise OSError(errno.ENOENT, 'Not found')

    def readdir(self, path, fh):
        print(f"DEBUG: readdir called for {path}")
        return ['.', '..'] + [f.lstrip('/') for f in self.files.keys()]

    def read(self, path, size, offset, fh):
        if path in self.files:
            return self.files[path][offset:offset + size]
        raise OSError(errno.ENOENT, 'Not found')

    def write(self, path, data, offset, fh):
        # Simplistic write: just overwrite the entire file content
        self.files[path] = data
        return len(data)

if __name__ == '__main__':
    # Usage: python3 zero_fs.py <mount_point>
    if len(sys.argv) != 2:
        print('Usage: zero_fs.py <mount_point>')
        sys.exit(1)
    
    mountpoint = sys.argv[1]
    FUSE(ZeroFS(), mountpoint, foreground=True, allow_other=True)
