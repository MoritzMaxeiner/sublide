import sublime
import sublime_plugin

from subprocess import Popen, PIPE, TimeoutExpired
from itertools import chain, repeat
from functools import reduce
from codecs import escape_decode

from sublide.util import is_dlang, open_file_byte_offset, goto_offset, encoding_offset_to_char_offset, char_offset_to_encoding_offset
import sublide.dub

class Server(sublime_plugin.ViewEventListener):

	class PortInUseException(Exception):
		pass

	class Instance:

		def __init__(self, path, port, include_paths):
			self.port = port
			args = list(chain([path, '--tcp', '--port', str(port), '--loglevel', 'error'],
			                  chain.from_iterable(zip(repeat('-I'), include_paths))))
			self.process = Popen(args)
			try:
				self.process.wait(0.05)
				raise Server.PortInUseException
			except TimeoutExpired:
				pass

		def close(self):
			if self.process is not None:
				self.process.kill()
				self.process.wait()
				self.process = None

	@classmethod
	def is_applicable(cls, settings):
		return is_dlang(settings.get('syntax'))
	@classmethod
	def applies_to_primary_view_only(cls):
		return True

	refCount = 0
	instance = None

	def __init__(self, view):
		type(self).refCount += 1
		if type(self).refCount == 1:
			type(self).start()

	def __del__(self):
		type(self).refCount -= 1
		if type(self).refCount == 0:
			if Server.instance is not None:
				type(self).stop()

	@classmethod
	def start(cls):
		assert cls.instance is None
		for port in range(settings.get('dcd_server_port_range')[0], settings.get('dcd_server_port_range')[1] + 1):
			try:
				app_path = settings.get('dcd_server_app_path')
				cls.instance = cls.Instance(app_path, port, settings.get('dcd_server_include_paths'))
			except FileNotFoundError:
				print('sublide: DCD functionality not available, application \"' + app_path + '\" not found')
				settings.add_on_change('dcd-server', cls.start)
				break
			except cls.PortInUseException:
				continue
			else:
				Client.add_include_paths(list(chain.from_iterable(sublide.dub.DUB.cached_include_paths.values())))
				settings.add_on_change('dcd-server', cls.restart)
				break

	@classmethod
	def stop(cls):
		settings.clear_on_change('dcd-server')

		assert cls.instance is not None
		cls.instance.close()
		cls.instance = None

	@classmethod
	def restart(cls):
		cls.stop()
		cls.start()


class Client(sublime_plugin.EventListener):

	def on_query_completions(self, view, prefix, locations):
		if not is_dlang(view.settings().get('syntax')) or Server.instance is None:
			return

		point = locations[0] - len(prefix)
		if (view.substr(point) != '.'):
			point = locations[0]

		completions_type, completions = type(self).get_completions(view, point)
		if completions_type == 'identifiers':
			return ([self.parse_identifiers(line) for line in completions], sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
		else:
			return

	def on_modified_async(self, view):
		if not is_dlang(view.settings().get('syntax')) or settings.get('dcd_calltip_disable') or Server.instance is None:
			return

		point = view.sel()[0].begin()
		trigger = view.substr(point - 1)
		if trigger == '(' or trigger == ',':
			completions_type, completions = type(self).get_completions(view, point)
			if completions_type == 'calltips':
				# Limit the popup window's height
				max_height_in_dip = settings.get('dcd_calltip_popup_max_height') * view.line_height()
				# Base the popup window's width on the longest line to show
				width_in_dip = (4 + reduce(max, map(lambda line: len(line), completions))) * view.em_width()

				view.show_popup('<br>'.join(completions), sublime.COOPERATE_WITH_AUTO_COMPLETE | sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=point, max_width=width_in_dip, max_height=max_height_in_dip)
		if not view.settings().get('auto_match_enabled') and trigger == ')':
			view.hide_popup()

	def on_hover(self, view, point, hover_zone):
		if not is_dlang(view.settings().get('syntax')) or Server.instance is None:
			return

		if hover_zone == sublime.HOVER_TEXT:
			doc = type(self).get_documentation(view, point)
			if doc is None:
				return

			# Limit the popup window's height
			max_height_in_dip = settings.get('dcd_documentation_popup_max_height') * view.line_height()
			# Base the popup window's width on the longest line to show
			width_in_dip = (4 + reduce(max, map(lambda line: len(line), doc.splitlines()))) * view.em_width()

			# Translate whitespace to HTML
			#   newline -> break tag
			#   space   -> space entity
			#   tab     -> 4 space entities
			doc = doc.replace('\n', '<br>').replace(' ', '&nbsp;').replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')

			view.show_popup(doc, flags=sublime.COOPERATE_WITH_AUTO_COMPLETE | sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=point, max_width=width_in_dip, max_height=max_height_in_dip)

	@classmethod
	def get_completions(cls, view, point):
		output = cls.__exec(['-c', str(char_offset_to_encoding_offset(view, point, 'utf-8'))], view.substr(sublime.Region(0, view.size())).encode('utf-8')).decode('utf-8').splitlines()
		if len(output) == 0:
			return None, []
		return output.pop(0), output

	@classmethod
	def get_symbol_location(cls, view, point):
		output = cls.__exec(['-c', str(char_offset_to_encoding_offset(view, point, 'utf-8')), '--symbolLocation'], view.substr(sublime.Region(0, view.size())).encode('utf-8')).decode('utf-8').splitlines()
		if len(output) == 0 or output[0] == 'Not found':
			return None, None
		return output[0].split('\t')

	@classmethod
	def get_documentation(cls, view, point):
		# Get UTF-8 encoded output
		doc = cls.__exec(['-c', str(char_offset_to_encoding_offset(view, point, 'utf-8')), '--doc'], view.substr(sublime.Region(0, view.size())).encode('utf-8'))
		if len(doc) == 0:
			return None
		# Remove escaping without touching code points encoded as multiple code units
		doc = escape_decode(doc)[0]
		# Decode from UTF-8
		doc = doc.decode('utf-8')
		return doc

	@classmethod
	def add_include_paths(cls, include_paths):
		if (len(include_paths) > 0):
			cls.__exec(list(chain.from_iterable(zip(repeat('-I'), include_paths))))

	@classmethod
	def __exec(cls, args, stdin=[]):
		assert Server.instance is not None
		try:
			app_path = settings.get('dcd_client_app_path')
			instance = Popen([app_path, '--tcp', '--port', str(Server.instance.port)] + args, stdin=PIPE, stdout=PIPE)
		except FileNotFoundError:
			print('sublide: DCD functionality not available, application \"' + app_path + '\" not found')
			return b''
		else:
			return instance.communicate(stdin)[0]

	@classmethod
	def parse_identifiers(cls, line):
		parts = line.split('\t')
		if len(parts) == 2:
			return parts[0] + '\t' + _completion_kind_map.get(parts[1], ' '), parts[0]
		else:
			return None


class DcdGotoDefinitionCommand(sublime_plugin.TextCommand):
	def is_enabled(self):
		return is_dlang(self.view.settings().get('syntax')) and Server.instance is not None
	def run(self, edit):
		file_name, offset = Client.get_symbol_location(self.view, self.view.sel()[0].a)
		if file_name is not None and offset is not None:
			if file_name != 'stdin':
				open_file_byte_offset(file_name, int(offset), 'utf-8')
			else:
				goto_offset(self.view, encoding_offset_to_char_offset(self.view, int(offset), 'utf-8'))


class DcdRestartServerCommand(sublime_plugin.WindowCommand):
	def is_enabled(self):
		return Server.instance is not None
	def run(self):
		Server.restart()

class DcdRefreshIncludePathsCommand(sublime_plugin.WindowCommand):
	def is_enabled(self):
		return Server.instance is not None
	def run(self):
		include_paths = sublide.dub.DUB.refresh_include_paths()
		Client.add_include_paths(include_paths)

_completion_kind_map = {
	'c': 'class',
	'i': 'interface',
	's': 'struct',
	'u': 'union',
	'v': 'variable',
	'm': 'member variable',
	'k': 'keyword',
	'f': 'function',
	'g': 'enum',
	'e': 'enum member',
	'P': 'package',
	'M': 'module',
	'a': 'array',
	'A': 'associative array',
	'l': 'alias',
	't': 'template',
	'T': 'mixin template'
}


def plugin_loaded():
	global settings
	settings = sublime.load_settings('sublide.sublime-settings')