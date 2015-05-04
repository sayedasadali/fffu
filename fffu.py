"""
ff4f.py
FUSE Filesystem for Flickr
Copyright 2015 Sayed Asad Ali <sayedasad@ucsd.edu>

THIS SOFTWARE IS SUPPLIED WITHOUT WARRANTY OF ANY KIND, AND MAY BE
COPIED, MODIFIED OR DISTRIBUTED IN ANY WAY, AS LONG AS THIS NOTICE
AND ACKNOWLEDGEMENT OF AUTHORSHIP REMAIN.

"""

import datetime
import logging
from StringIO import StringIO
import os
import sys
import errno
import flickrapi
import fs
import fs.base
import fs.errors
import fuse
import stat
import time
from fuse import FUSE, FuseOSError, Operations
from lxml import etree
# temporary import
import xml.etree.cElementTree as ET

def initLogging():
	# logformat = '%(asctime)-12s:[%(levelname)s] %(message)s'
	logformat = '[%(levelname)s] %(message)s'
	logfile = 'logs/' + datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S') + '.log'
	logging.basicConfig( level = logging.INFO
	# , filename = logfile
	, format   = logformat
	)
	formatter = logging.Formatter(logformat, '%Y-%m-%d %H:%M:%S')
	# console   = logging.StreamHandler()
	# console.setLevel(logging.DEBUG)
	# console.setFormatter(formatter)
	# logging.getLogger('').addHandler(console)

class FFFU(Operations):
	""" FFFU system object """
	def __init__(self, root):
		super(FFFU, self).__init__()
		self._cache  = {}
		self.root    = root

		self.rootxml = etree.Element( 'root'
			                        , st_type  ='d'
			                        )
		#TODO search for fs.xml.png 
		# https://www.flickr.com/services/api/flickr.photos.search.html
		fsfile = open('fs.xml', 'r')
		self.rootree = etree.parse(fsfile)
		fsfile.close()

		self.logger  = logging.getLogger('FF4F')
		self.logger.debug('init')

		api_key      = '496f02eaab89d5b4dd5651a51fcb68bd'
		api_secret   = '768e8faf9d827aad'
		api_token    = '72157652063976241-07f9b09c99760c7e'

		self.flickr       = flickrapi.FlickrAPI(api_key, api_secret, token=api_token)
		if not self._test_echo():
			raise RuntimeError('flickr.test.echo failed - aborting mount')

		# can use this to get context
		# fuse.fuse_get_context()

	def destroy(self, private_data):
		self.logger.info('FFFU terminated')
		return

	# Filesystem methods
	# ==================

	def getattr(self, path, fh=None):
		# fffu implementation
		# TODO dig deeper into the extended attributes for '/._.'
		# extended attributes not supported for now
		# will raise ValueError: Invalid tag name u'._*'
		self.logger.debug('getattr - %s' % (path))
		curdir = self._get_dir(path)

		# dir/file entry doesn't exist
		# raise appropriate error so that mkdir does its thing
		if curdir is None:
			raise FuseOSError(errno.ENOENT)

		#TODO transition from usage of 'f' 'd' etc to numbers
		# xmld  = dict((key, int(curdir.attrib[key])) for key in curdir.attrib.keys())
		xmld  = dict((key, int(curdir.attrib[key])) for key in ('st_atime', 'st_ctime',
				'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
		return xmld

	def access(self, path, mode):
		self.logger.debug('access')
		#TODO fffu equivalent
		# full_path = self._full_path(path)
		# if not os.access(full_path, mode):
		# 	raise FuseOSError(errno.EACCES)
		return 0

	def readlink(self, path):
		self.logger.info('readlink')
		#TODO fffu equivalent
		# pathname = os.readlink(self._full_path(path))
		# if pathname.startswith("/"):
		# 	# Path name is absolute, sanitize it.
		# 	return os.path.relpath(pathname, self.root)
		# else:
		# 	return pathname
		raise FuseOSError(errno.ENOSYS)

	def opendir(self, path):
		self.logger.debug('opendir')
		return 0

	def readdir(self, path, fh):
		dirs = ['.', '..']
		curdir = self._get_dir(path)
		if curdir is not None:
			for child in curdir.iterchildren('*'):
				dirs.append(child.tag)
		self.logger.debug('readdir - path: %s dirs: %s' % (path, str(dirs)))
		for r in dirs:
			yield r

	def mknod(self, path, mode, dev):
		self.logger.info('mknod')
		#TODO fffu equivalent
		# rarely accessed
		# return os.mknod(self._full_path(path), mode, dev)
		raise FuseOSError(errno.ENOSYS)

	def mkdir(self, path, mode):
		# fffu initial implementation only supports mkdir -p
		self.logger.debug('mkdir %s %s'%(path, str(mode)))
		curdir = self._get_dir(path)
		if curdir is None:
			self._add_node(path, mode, st_type='d')
		return 0

	def unlink(self, path):
		self.logger.debug('unlink - %s' % path)
		# FFFU
		# first-pass just remove
		cur_file = self._get_dir(path)
		os.remove(self._full_path(cur_file.attrib['st_inode']))
		self._del_node(path)
		# return os.unlink(self._full_path(path))

	def rmdir(self, path):
		self.logger.debug('rmdir %s'%path)
		self._del_node(path)
		return 0

	def symlink(self, name, target):
		# this can get complex, come back to it later
		self.logger.info('symlink')
		raise FuseOSError(errno.ENOSYS)
		# return os.symlink(name, self._full_path(target))

	def link(self, target, name):
		# same as symlink
		self.logger.info('link')
		raise FuseOSError(errno.ENOSYS)
		# return os.link(self._full_path(target), self._full_path(name))


	def rename(self, old, new):
		self.logger.debug('rename %s %s' %(old, new))
		olddir = self._get_dir(old)
		olddir.getparent().remove(olddir)
		newpar = self._get_parent(new)

		#change the name
		olddir.tag = new[new.rindex('/') + 1:]
		newpar.append(olddir)
		self._save_fs()

		return 0

	def chmod(self, path, mode):
		# fffu implementation
		self.logger.debug('chmod')
		curdir = self._get_dir(path)
		self.logger.debug('chmod - cur: %s new: %s' % (curdir.attrib['st_mode'], mode))
		curdir.attrib['st_mode'] = str(mode)

		self._save_fs()

		return 0

	def chown(self, path, uid, gid):
		#TODO
		self.logger.info('chown')
		raise FuseOSError(errno.ENOSYS)

	def utimens(self, path, times=None):
		curdir = self._get_dir(path)
		new_time = str(int(time.time()))
		self.logger.debug('utimens - path: %s new_time: %s old_time %s' % (path, new_time, curdir.attrib['st_atime']))
		curdir.attrib['st_atime'] = new_time

		self._save_fs()
		return 0

	def statfs(self, path):
		# fffu implementation
		# ideally this should let user know
		# about the space left on the flickr account
		self.logger.debug('statfs - %s root: %s' % (path, self.root))

		# not implementing now as it is a very frequent function call
		# ret = self.flickr.test_echo()		
		# retstr = ET.tostring(ret, encoding='utf8', method='xml')
		# print retstr

		stats = { 'f_bavail' : 0
				, 'f_bfree'  : 0
				, 'f_blocks' : 0
				, 'f_bsize'  : 0
				, 'f_avail'  : 0
				, 'f_ffree'  : 0
				, 'f_files'  : 0
				, 'f_flag'   : 0
				, 'f_frsize' : 0
				, 'f_namemax': 0
				}

		return stats

	# File methods
	# ============

	def open(self, path, flags):
		# download file
		# open file
		# if file is already downloaded just open it
		# no need to store it in a directory etc.

		cur_file = self._get_dir(path)
		full_path = self._full_path(cur_file.attrib['st_inode'])
		self.logger.debug('open - %s' % (path))
		return os.open(full_path, flags)

	def create(self, path, mode, fi=None):
		# create a local file
		# get inode number 
		# create local file in local directory
		new_node  = self._add_node(path, mode, st_type='f')

		full_path = self._full_path(new_node.attrib['st_inode'])
		self.logger.info('create - path %s mode %s full_path %s' % (path, mode, full_path))
		tmpfile = full_path + '.png'
		with open('fffu.png', 'rb') as src, open(tmpfile, 'wb') as dest:
			dest.write(src.read())

		ret = self.flickr.upload(filename=tmpfile, is_public=0)
		new_node.attrib['photo_id'] = ret.find('photoid').text

		os.remove(tmpfile)
		self._save_fs()
		return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

	def read(self, path, length, offset, fh):
		self.logger.debug('read - %s' % path)
		os.lseek(fh, offset, os.SEEK_SET)
		return os.read(fh, length)

	def write(self, path, buf, offset, fh):
		self.logger.debug('write - %s buf: %s' % (path, buf))
		os.lseek(fh, offset, os.SEEK_SET)
		return os.write(fh, buf)

	def truncate(self, path, length, fh=None):
		self.logger.debug('truncate')
		cur_file = self._get_dir(path)
		full_path = self._full_path(cur_file.attrib['st_inode'])
		with open(full_path, 'r+') as f:
			f.truncate(length)

	def flush(self, path, fh):
		self.logger.debug('flush')
		return os.fsync(fh)

	def release(self, path, fh):
		self.logger.info('release - path %s' % path)
		self._get_dir(path).attrib['st_size'] = str(os.fstat(fh).st_size)
		self._save_fs()

		return os.close(fh)

	def fsync(self, path, fdatasync, fh):
		self.logger.debug('fsync')
		return self.flush(path, fh)

	# Helpers
	# =======
	def _full_path(self, partial):
		self.logger.debug('_full_path: %s'% partial)
		if partial.startswith("/"):
			partial = partial[1:]
		path = os.path.join(self.root, partial)
		return path

	def _get_dir(self, path):
		if path == '/':
			return self.rootree.getroot()
		else:
			return self.rootree.find(path)

	def _get_parent(self, path):
		# use only if child node doesn't exist
		# else use getparent()
		# assuming / as directory separator
		parentPath = path[:path.rfind('/')]
		if parentPath == '':
			parentPath = '/'
		return self._get_dir(parentPath)

	def _test_echo(self):
		ret = self.flickr.test_echo()		
		# retstr = ET.tostring(ret, encoding='utf8', method='xml')
		# print retstr
		if ret.attrib and ret.attrib['stat'] == 'ok':
			return True
		return False

	def _save_fs(self):
		fsfile = open('fs.xml', 'w')
		self.rootree.write(fsfile)
		fsfile.close()

	def _data_to_png(self, fname):
		"""takes fd of any file
		   appends file to dummy png
		   saves resulting file
		"""
		file(fname + '.png', 'wb').write(file('fffu.png', 'rb').read() + file(fname, 'rb').read())

	def _png_to_data(self, fname):
		pass

	def _get_inode(self):
		""" temporary function to return dummy inodes to create files. seed value based on root"""
		cur_inode = self.rootree.getroot().attrib['st_inode']
		self.rootree.getroot().attrib['st_inode'] = str(int(cur_inode) + 1)
		return cur_inode

	def _add_node(self, path, mode, st_type=None, st_inode=None):
		self.logger.info('_add_node path: %s mode: %s st_type: %s flickr: %s'%(path, str(mode), st_type, st_inode))
		parentDir  = self._get_parent(path)

		# convert all attributes to string
		ctx = fuse.fuse_get_context()
		st_size  = str(0)
		st_mode  = str(mode)
		st_uid   = str(ctx[0])
		st_gid   = str(ctx[1])
		st_dev   = str(0)
		st_inode = self._get_inode()
		st_nlink = str(0)
		st_time  = str(int(time.time()))

		# create new node in the xml tree
		new_node = etree.Element(path[path.rfind('/') + 1:], st_type  = st_type
			                                               , st_size  = st_size 
			                                               , st_mode  = st_mode 
			                                               , st_uid   = st_uid
			                                               , st_gid   = st_gid
			                                               , st_dev   = st_dev
			                                               , st_inode = st_inode
			                                               , st_nlink = st_nlink
			                                               , st_atime = st_time
			                                               , st_mtime = st_time
			                                               , st_ctime = st_time
			                                               )
		parentDir.append(new_node)

		self._save_fs()
		return new_node

	def _del_node(self, path):
		curdir = self._get_dir(path)
		if curdir is not None:
			self.logger.debug('removing node: %s' % path)
			parentDir = self._get_parent(path)
			parentDir.remove(curdir)

		self._save_fs()
		return 0


if __name__ == '__main__':
	lw = 40
	print '*' * lw
	print 'FFFU (FUSE Flickr Filesystem for U)'.center(lw)
	print '*' * lw

	initLogging()
	logging.debug('started')
	mntpoint = sys.argv[1]
	root     = sys.argv[2]
	FUSE(FFFU(root), mntpoint, foreground=True)