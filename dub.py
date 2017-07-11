import sublime
import sublime_plugin

import json
import os.path
from itertools import chain
from subprocess import Popen, PIPE

from sublide.util import is_dlang
import sublide.dcd

class DUB(sublime_plugin.ViewEventListener):

	@classmethod
	def is_applicable(cls, settings):
		return is_dlang(settings.get('syntax'))
	@classmethod
	def applies_to_primary_view_only(cls):
		return True

	cached_include_paths = dict()
	package_filenames = ['dub.json', 'package.json', 'dub.sdl']

	def __init__(self, view):
		window_folders = view.window().folders()
		for folder in window_folders:
			if not folder in type(self).cached_include_paths.keys():
				type(self).cached_include_paths[folder] = type(self).get_include_paths(folder)
				if sublide.dcd.Server.instance is not None:
					sublide.dcd.Client.add_include_paths(type(self).cached_include_paths[folder])

	@classmethod
	def refresh_include_paths(cls):
		cls.cached_include_paths = dict()
		for folder in chain.from_iterable(window.folders() for window in sublime.windows()):
			cls.cached_include_paths[folder] = cls.get_include_paths(folder)
		return cls.cached_include_paths

	@classmethod
	def get_include_paths(cls, folder):
		include_paths = set()
		if cls.has_package_file(folder):
			description = cls.describe(folder)
			if description is not None:
				for index, package in enumerate(description['packages']):
					base_path = os.path.abspath(package['path'])
					for sub_path in package['importPaths']:
						include_paths.add(os.path.join(base_path, sub_path))
		return include_paths

	@classmethod
	def has_package_file(cls, path):
		for f in cls.package_filenames:
			p = os.path.join(path, f)
			if (os.path.exists(p)):
				return True
		return False

	@classmethod
	def describe(cls, path):
		description = cls.__exec(['describe', '--root=' + path, "--vquiet"])
		if len(description) == 0:
			return None
		try:
			return json.loads(description)
		except ValueError:
			return None

	@classmethod
	def __exec(cls, args):
		try:
			app_path = settings.get('dub_app_path')
			instance = Popen([app_path] + args, stdout=PIPE)
		except FileNotFoundError:
			print('sublide: DUB functionality not available, application \"' + app_path + '\" not found')
			return []
		else:
			return instance.communicate()[0].decode('utf-8')


def plugin_loaded():
	global settings
	settings = sublime.load_settings('sublide.sublime-settings')