#!/usr/bin/env python
#
# Connector for elFinder File Manager
# author Troex Nevelin <troex@fury.scancode.ru>


import binascii
import cgi
import cgitb
import mimetypes
import os
import os.path
import re
import sys
import simplejson
from datetime import datetime, date, time

print "Content-type: text/html\n"

cgitb.enable()

class elFinder():
	"""Connector for elFinder"""

	_options = {
		'root': './',
		'URL': '',
		'rootAlias': 'Home',
		'ignoreDotFiles': True, # TODO
		'debug': True,
		'dirSize': True,
		'fileUmask': 0666,
		'dirUmask': 0755,
		'tmbDir': '.tmb',
		'tmbSize': 48,
		'allowTypes': [],
		'allowExts': [],
		'denyTypes': [],
		'denyExts': [],   
		'allowURLs': [],
		'disabled': [],
		'aclObj': None,
		'aclRole': 'user',
		'defaults': {
			'read': True,
			'write': True,
			'mkdir': True,
			'upload': True,
			'rm': True,
			'rmdir': True
		},
		'perms': []
	}

	_commands = {
		'open':    '__open',
		'reload':  '__reload',
		'mkdir':   '__mkdir',
		'mkfile':  '__mkfile',
		'rename':  '__rename',
		'upload':  '__upload',
		'paste':   '__paste',
		'rm':      '__rm',
		'duplicate': '__duplicate',
		'edit':    '__edit',
		'extract': '__extract',
		'resize':  '__resize',
		'geturl':  '__geturl',
		'tmb':     '__thumbnails'
	}

	_request = {}
	_errorData = {}


	def __init__(self, opts):
		for opt in opts:
			self._options[opt] = opts.get(opt)


	def run(self):
		possible_fields = ['cmd', 'target', 'current', 'name', 'rm[]']
		form = cgi.FieldStorage()
		for field in possible_fields:
			if field in form:
				self._request[field] = form.getvalue(field)

		response = {}		
		# print self._request
		if 'cmd' in self._request:
			if self._request['cmd'] in self._commands:
				cmd = self._commands[self._request['cmd']]
				func = getattr(self, '_' + self.__class__.__name__ + cmd, None)
				if callable(func):
					if cmd == '__open':
						response = func(False)
					else:
						response = func()
		else:
			response['disabled'] = self._options['disabled']
			response.update(self.__reload())
		
		print simplejson.dumps(response)


	def __mkfile(self):
		"""Create new file"""
		response = {}
		name = current = None
		curDir = newFile = None
		if 'name' in self._request and 'current' in self._request:
			name = self._request['name']
			current = self._request['current']
			curDir = self.__findDir(current, None)
			newFile = os.path.join(curDir, name)

		if not curDir or not name:
			response['error'] = 'Invalid parameters'
		elif not self.__isAllowed(curDir, 'write'):
			response['error'] = 'Access denied!'
		elif not self.__checkName(name):
			response['error'] = 'Invalid name'
		elif os.path.exists(newFile):
			response['error'] = 'File or folder with the same name already exists'
		else:
			try:
				open(newFile, 'w').close()
				response = self.__content(curDir, False)
			except:
				response['error'] = 'Unable to create file'

		return response



	def __rm(self):
		response = {}
		current = rmList = None
		curDir = rmFile = None
		if 'current' in self._request and 'rm[]' in self._request:
			current = self._request['current']
			rmList = self._request['rm[]']
			curDir = self.__findDir(current, None)

		if not rmList or not curDir:
			response['error'] = 'Invalid parameters'
			return response

		if not isinstance(rmList, list):
			rmList = [rmList]

		for rm in rmList:
			rmFile = self.__find(rm, curDir)
			if not rmFile: continue
			self.__remove(rmFile)

		if self._errorData: response['errorData'] = self._errorData
		response.update(self.__content(curDir, True))

		return response


	def __remove(self, target):
		if not self.__isAllowed(target, 'rm'):
			self.__setErrorData(target, 'Access denied!')

		if not os.path.isdir(target):
			try:
				os.unlink(target)
				return True
			except:
				self.__setErrorData(target, 'Remove failed')
				return False
		else:
			try:
				for i in os.listdir(target):
					if self.__isAccepted(i):
						self.__remove(i)
			except:
				pass

			try:
				os.rmdir(target)
				return True
			except:
				self.__setErrorData(target, 'Remove failed')
				return False
		pass


	def __isAccepted(self, target):
		if target == '.' or target == '..':
			return False
		if self._options['ignoreDotFiles'] and target[0:1] == '.':
			return False
		return True


	def __find(self, fhash, parent):
		"""Find file/dir by hash"""
		fhash = str(fhash)
		if os.path.isdir(parent):
			for i in os.listdir(parent):
				path = os.path.join(parent, i)
				if fhash == self.__hash(path):
					return path
		return None


	def __rename(self):
		"""Rename file or dir"""
		response = {}
		current = name = target = None
		curDir = curName = newName = None
		if 'name' in self._request and 'current' in self._request and 'target' in self._request:
			name = self._request['name']
			current = self._request['current']
			target = self._request['target']
			curDir = self.__findDir(current, None)
			curName = self.__find(target, curDir)
			newName = os.path.join(curDir, name)

		if not curDir or not curName:
			response['error'] = 'File does not exists'
		elif not self.__isAllowed(curDir, 'write'):
			response['error'] = 'Access denied!'
		elif not self.__checkName(name):
			response['error'] = 'Invalid name'
		elif os.path.exists(newName):
			response['error'] = 'File or folder with the same name already exists'
		else:
			try:
				os.rename(curName, newName)
				response = self.__content(curDir, os.path.isdir(newName))
			except:
				response['error'] = 'Unable to rename file'

		return response


	def __mkdir(self):
		"""Create new directory"""
		response = {}
		current = None
		path = None
		newDir = None
		if 'name' in self._request and 'current' in self._request:
			name = self._request['name']
			current = self._request['current']
			path = self.__findDir(current, None)
			newDir = os.path.join(path, name)

		if not path:
			response['error'] = 'Invalid parameters'
		elif not self.__isAllowed(path, 'write'):
			response['error'] = 'Access denied!'
		elif not self.__checkName(name):
			response['error'] = 'Invalid name'
		elif os.path.exists(newDir):
			response['error'] = 'File or folder with the same name already exists'
		else:
			try:
				os.mkdir(newDir, int(self._options['dirUmask']))
				response = self.__content(path, True)
			except:
				response['error'] = 'Unable to create folder'

		return response


	def __checkName(self, name):
		"""Check for valid file/dir name"""
		pattern = r'[\/\\\:\<\>]'
		if re.search(pattern, name):
			return False
		return True


	def __reload(self):
		return self.__open(True)


	def __open(self, tree):
		"""Open file or directory"""
		# try to open file
		if 'current' in self._request:
			pass
		# try dir
		else:
			response = {}
			path = self._options['root']
			
			if 'target' in self._request:
				target = self.__findDir(int(self._request['target']), None)
				if not target:
					response['warning'] = 'Directory does not exists'
				elif not (os.access(target, os.R_OK) and self.__isAllowed(target, 'read')):
					response['warning'] = 'Access denied'
				else:
					path = target

			response.update(self.__content(path, tree))
			
			return response
		pass


	def __content(self, path, tree):
		"""CWD + CDC + maybe(TREE)"""
		response = {}
		response['cwd'] = self.__cwd(path)
		response['cdc'] = self.__cdc(path)

		if tree:
			fhash = self.__hash(self._options['root'])
			if self._options['rootAlias']:
				name = self._options['rootAlias']
			else:
				name = os.path.basename(self._options['root'])
			response['tree'] = [
				{
					'hash': fhash,
					'name': name,
					'read': True,
					'dirs': self.__tree(self._options['root'])
				}
			]
		return response


	def __cwd(self, path):
		"""Current Working Directory"""
		name = os.path.basename(path)
		if path == self._options['root']:
			name = self._options['rootAlias']
			root = True
		else:
			root = False

		if self._options['rootAlias']:
			basename = self._options['rootAlias']
		else:
			basename = os.path.basename(self._options['root'])
		
		rel = basename + path[len(self._options['root']):]

		response = {
			'hash': self.__hash(path),
			'name': name,
			'rel': rel,
			'size': 0,
			'date': datetime.fromtimestamp(os.stat(path).st_mtime).strftime("%d %b %Y %H:%M"),
			'read': True,
			'write': os.access(path, os.W_OK) and self.__isAllowed(path, 'write'),
			'rm': not root and self.__isAllowed(path, 'rm'),
			'uplMaxSize': '128M' # TODO
		}
		return response


	def __cdc(self, path):
		"""Current Directory Content"""
		files = []
		dirs = []

		for f in os.listdir(path):
			if not self.__isAccepted(f): continue
			pf = os.path.join(path, f)
			info = {}
			info = self.__info(pf)
			info['hash'] = self.__hash(pf)
			if info['type'] == 'dir':
				dirs.append(info)
			else:
				files.append(info)

		dirs.extend(files)
		return dirs


	def __hash(self, input):
		"""Hash of path can be any uniq"""
		return str(binascii.crc32(input))


	def __findDir(self, fhash, path):
		"""Find directory by hash"""
		fhash = str(fhash)
		if not path:
			path = self._options['root']
			if fhash == self.__hash(path):
				return path

		if not os.path.isdir(path): return None

		for d in os.listdir(path):
			pd = os.path.join(path, d)
			if os.path.isdir(pd) and not os.path.islink(pd):
				if fhash == self.__hash(pd):
					return pd
				else:
					ret = self.__findDir(fhash, pd)
					if ret:
						return ret

		return None


	def __tree(self, path):
		"""Return directory tree starting from path
		FULL
		"""
		tree = []
		
		if not os.path.isdir(path): return ''
		if os.path.islink(path): return ''

		for d in os.listdir(path):
			pd = os.path.join(path, d)
			if os.path.isdir(pd) and not os.path.islink(pd) and self.__isAccepted(d):
				fhash = self.__hash(pd)
				read = os.access(pd, os.R_OK) and self.__isAllowed(pd, 'read')
				write = os.access(pd, os.W_OK) and self.__isAllowed(pd, 'write')
				if read:
					dirs = self.__tree(pd)
				else:
					dirs = ''
				element = {
					'hash': fhash,
					'name': d,
					'read': read,
					'write': write,
					'dirs': dirs
				}
				tree.append(element)

		if len(tree) == 0: return ''
		else: return tree
	

	def __info(self, path):
		mime = ''
		filetype = 'file'
		if os.path.isfile(path): filetype = 'file'
		if os.path.isdir(path):  filetype = 'dir'
		if os.path.islink(path): filetype = 'link'
		
		stat = os.lstat(path)

		info = {
			'name': os.path.basename(path),
			'hash': self.__hash(path),
			'type': filetype,
			'mime': 'directory' if filetype == 'dir' else self.__mimetype(path),
			'date': datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y %H:%M"),
			'size': self.__dirSize(path) if filetype == 'dir' else stat.st_size,
			'read': os.access(path, os.R_OK),
			'write': os.access(path, os.W_OK),
			'rm': self.__isAllowed(path, 'rm')
		}
		
		if filetype == 'link':
			path = self.__readlink(path)
			if not path:
				info['mime'] = 'unknown'
				return info

			if os.path.isdir(path):
				info['mime'] = 'directory'
			else:
				info['mime'] = self.__mimetype(path)

			if self._options['rootAlias']:
				basename = self._options['rootAlias']
			else:
				basename = os.path.basename(self._options['root'])
			
			info['linkTo'] = basename + path[len(self._options['root']):]
			info['link'] = self.__hash(path)
			info['read'] = info['read'] and self.__isAllowed(path, 'read')
			info['write'] = info['write'] and self.__isAllowed(path, 'write')
			info['rm'] = self.__isAllowed(path, 'rm')
			
			# TODO more actions here
			# TODO image sizes
		
		return info


	def __mimetype(self, path):
		return mimetypes.guess_type(path)[0]


	def __readlink(self, path):
		"""Read link and return real path if not broken"""
		target = os.readlink(path);
		if not target[0] == '/':
			target = os.path.join(os.path.dirname(path), target)
		target = os.path.normpath(target)
		if os.path.exists(target):
			if not target.find(self._options['root']) == -1:
				return target
		return False


	def __dirSize(self, path):
		total_size = 0
		for dirpath, dirnames, filenames in os.walk(path):
			for f in filenames:
				fp = os.path.join(dirpath, f)
				if os.path.exists(fp):
					total_size += os.stat(fp).st_size
		return total_size


	def __isAllowed(self, path, action):
		return True


	def __setErrorData(self, path, msg):
		"""Collect error/warning messages"""
		self._errorData[path] = msg


elFinder({
	'root': '/Users/troex/Sites/git/elrte/files',
	'rootAlias': ''
}).run()

#print os.environ
