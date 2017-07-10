# Provide linting only if SublimeLinter framework is installed
try:
	from SublimeLinter.lint import Linter, util

	class Dscanner(Linter):
		"""Provides D linting via DScanner to the SublimeLinter framework."""

		syntax = 'd'
		cmd = ['dscanner', '-S', 'stdin']
		executable = None
		version_args = '--version'
		version_re = r'\bv(?P<version>\d+\.\d+\.\d+)'
		version_requirement = '>= 0.4.0'
		regex = r'^[^(]+\((?P<line>\d+):(?P<col>\d+)\)\[(?:(?P<error>error)|(?P<warning>warn))\]: (?P<message>.+)'
		multiline = False
		line_col_base = (1, 1)
		tempfile_suffix = None
		error_stream = util.STREAM_STDOUT
		selectors = {}
		word_re = None
		defaults = {}
		inline_settings = None
		inline_overrides = None
		comment_re = None
except ImportError:
	print('sublide: SublimeLinter framework not found, no dscanner-backed linting provided')