import sublime
import sublime_plugin

def is_dlang(syntax):
	"""Returns whether the given syntax corresponds to a D source file"""
	return syntax == 'Packages/D/D.sublime-syntax'

def goto_offset(view, offset):
	"""Given an offset into a view, shows the view and moves the cursor to the offset"""
	region = sublime.Region(offset)
	view.sel().clear()
	view.sel().add(region)
	view.show_at_center(region)

def char_offset_to_encoding_offset(view, char_offset, encoding):
	"""Given a character offset into a view, returns the corresponding byte offset w.r.t. to the given encoding"""
	assert char_offset <= view.size()
	encoded = view.substr(sublime.Region(0, char_offset)).encode(encoding)
	return len(encoded)

def encoding_offset_to_char_offset(view, byte_offset, encoding):
	"""Given a byte offset into a view w.r.t. the given encoding, returns the corresponding character offset"""
	assert byte_offset <= view.size()
	encoded = view.substr(sublime.Region(0, byte_offset)).encode(encoding)
	if len(encoded) == byte_offset:
		return byte_offset
	decoded = encoded[0:byte_offset].decode(encoding)
	return len(decoded)

def open_file_byte_offset(file_name, byte_offset, encoding):
	"""Similar to builtin open_file, but it opens the file at a byte offset w.r.t. to the given encoding"""
	class OnLoadListener:
		def __init__(self, view):
			self.view = view
			sublime_plugin.all_callbacks['on_load'].append(self)
		def on_load(self, view):
			if view.id() == self.view.id():
				sublime_plugin.all_callbacks['on_load'].remove(self)
				offset = encoding_offset_to_char_offset(view, byte_offset, encoding)
				goto_offset(view, offset)
	view = sublime.active_window().open_file(file_name)
	if view.is_loading():
		OnLoadListener(view)
	else:
		offset = encoding_offset_to_char_offset(view, byte_offset, encoding)
		goto_offset(view, offset)
	return view