# Copyright 2014 Google Inc. All Rights Reserved.
"""Utility functions for managing customer supplied encryption keys."""

import base64
import json

from googlecloudsdk.calliope import exceptions


EXPECTED_RECORD_KEY_KEYS = set(['uri', 'key'])
BASE64_KEY_LENGTH_IN_CHARS = 44


class MissingCsekKeyException(exceptions.ToolException):

  def __init__(self, resource):
    super(MissingCsekKeyException, self).__init__(
        'Key required for resource [{0}], but none found.'.format(resource))


class InvalidKeyFileException(exceptions.ToolException):
  """There's a problem in a CSEK file."""

  def __init__(self, base_message):
    super(InvalidKeyFileException, self).__init__(
        '{0}'.format(base_message))
    # TODO(user) Update this message to include
    # a lint to friendly documentation.


class BadPatternException(InvalidKeyFileException):
  """A (e.g.) url pattern is bad bad and why."""

  def __init__(self, pattern_type, pattern):
    self.pattern_type = pattern_type
    self.pattern = pattern
    super(BadPatternException, self).__init__(
        'Invalid value for [{0}] pattern: [{1}]'.format(
            self.pattern_type,
            self.pattern))


class InvalidKeyException(InvalidKeyFileException):
  """Indicate that a particular key is bad, why, and where."""

  def __init__(self, key, key_id, issue):
    self.key = key
    self.key_id = key_id
    self.issue = issue
    super(InvalidKeyException, self).__init__(
        'Invalid key, [{0}], for [{1}]: {2}'.format(
            self.key,
            self.key_id,
            self.issue))


def ValidateKey(base64_encoded_string, key_for):
  """ValidateKey(s, k) returns None or raises InvalidKeyException."""

  if len(base64_encoded_string) != 44:
    raise InvalidKeyException(
        base64_encoded_string, key_for,
        'Key should contain {0} characters (including padding), '
        'but is [{1}] characters long.'.format(
            BASE64_KEY_LENGTH_IN_CHARS,
            len(base64_encoded_string)))

  if base64_encoded_string[-1] != '=':
    raise InvalidKeyException(
        base64_encoded_string, key_for,
        'Bad padding.  Keys should end with an \'=\' character.')

  try:
    base64.standard_b64decode(base64_encoded_string)
  except TypeError as t:
    raise InvalidKeyException(
        base64_encoded_string, key_for,
        'Key is not valid base64: [{0}].'.format(t.message))


def AddCsekKeyArgs(parser, flags_about_creation=True):
  """Adds arguments related to csek keys."""

  # TODO(b/20883005)
  # We're temporarily disabling CSEK to allow cl/92889254 to land without
  # breaking our tests.
  return
  # pylint: disable=unreachable

  csek_key_file = parser.add_argument(
      '--csek-key-file',
      help=('Path to a csek key file'),
      metavar='FILE')
  csek_key_file.detailed_help = (
      'Path to a csek key file, mapping GCE resources to user managed '
      'keys to be used when creating, mounting, or snapshotting disks. ')
  # TODO(user)
  # Argument - indicates the key file should be read from stdin.'

  if flags_about_creation:
    no_require_csek_key_create = parser.add_argument(
        '--no-require-csek-key-create',
        help=('Allow creating of resources not protected by csek key.'),
        action='store_true')
    no_require_csek_key_create.detailed_help = (
        'When invoked with --csek-key-file gcloud will refuse to create '
        'resources not protected by a user managed key in the key file.  This '
        'is intended to prevent incorrect gcloud invocations from accidentally '
        'creating resources with no user managed key.  This flag disables the '
        'check and allows creation of resources without csek keys.')
  # TODO(b/20883005) remove:
  # pylint: enable=unreachable


class UriPattern(object):
  """A uri-based pattern that maybe be matched against resource objects."""

  def __init__(self, path_as_string):
    if not path_as_string.startswith('http'):
      raise BadPatternException('uri', path_as_string)
    self._path_as_string = path_as_string

  def Matches(self, resource):
    """Tests if its argument matches the pattern."""
    return self._path_as_string == resource.SelfLink()

  def __str__(self):
    return 'Uri Pattern: ' + self._path_as_string


class CsekKeyStore(object):
  """Represents a map from resource patterns to keys."""

  # Members
  # self._state: dictionary from UriPattern to a valid, base64-encoded key

  @staticmethod
  def FromFile(fname):
    """FromFile loads a CsekKeyStore from a file.

    Args:
      fname: str, the name of a file intended to contain a well-formed key file

    Returns:
      A MaterKeyStore, if found

    Raises:
      exceptions.BadFileException: there's a problem reading fname
      exceptions.InvalidKeyFileException: the key file failed to parse
        or was otherwise invalid
    """

    with open(fname) as infile:
      content = infile.read()

    return CsekKeyStore(content)

  @staticmethod
  def FromArgs(args):
    """FromFile attempts to load a CsekKeyStore from a command's args.

    Args:
      args: CLI args with a csek_key_file field set

    Returns:
      A CsekKeyStore, if a valid key file name is provided as csek_key_file
      None, if args.csek_key_file is None

    Raises:
      exceptions.BadFileException: there's a problem reading fname
      exceptions.InvalidKeyFileException: the key file failed to parse
        or was otherwise invalid
    """
    assert hasattr(args, 'csek_key_file')

    if args.csek_key_file is None:
      return None

    return CsekKeyStore.FromFile(args.csek_key_file)

  @staticmethod
  def _ParseAndValidate(s):
    """_ParseAndValidate(s) inteprets s as a csek key file.

    Args:
      s: str, an input to parse

    Returns:
      a valid state object

    Raises:
      InvalidKeyFileException: if the input doesn't parse or is not well-formed.
    """

    assert type(s) is str
    state = {}

    try:
      records = json.loads(s)

      if type(records) is not list:
        raise InvalidKeyFileException(
            "Key file's top-level element must be a JSON list.")

      for key_record in records:
        if type(key_record) is not dict:
          raise InvalidKeyFileException(
              'Key file records must be JSON objects, but [{0}] found.'.format(
                  json.dumps(key_record)))

        if set(key_record.keys()) != EXPECTED_RECORD_KEY_KEYS:
          raise InvalidKeyFileException(
              'Record [{0}] has incorrect json keys; [{1}] expected'.format(
                  json.dumps(key_record),
                  ','.join(EXPECTED_RECORD_KEY_KEYS)))

        pattern = UriPattern(key_record['uri'])
        ValidateKey(key_record['key'], pattern)

        state[pattern] = key_record['key']

    except ValueError:
      raise InvalidKeyFileException.FromCurrent()

    assert type(state) is dict
    return state

  def __len__(self):
    return len(self.state)

  def LookupKey(self, resource, raise_if_missing=False):
    """Search for the unique key corresponding to a given resource.

    Args:
      resource: the resource to find a key for.
      raise_if_missing: bool, raise an exception if the resource is not found.

    Returns:
      The base64 encoded string corresponding to the resource,
        or none if not found and not raise_if_missing.

    Raises:
      InvalidKeyFileException: if there are two records matching the resource.
      MissingCsekKeyException: if raise_if_missing and no key is found
        for the provided resoure.
    """

    assert type(self.state) is dict
    search_state = (None, None)

    for pat, key in self.state.iteritems():
      if pat.Matches(resource):
        # TODO(user) what's the best thing to do if there are multiple
        # matches?
        if search_state[0]:
          raise exceptions.InvalidKeyFileException(
              'Uri patterns [{0}] and [{1}] both match '
              'resource [{2}].  Bailing out.'.format(
                  search_state[0], pat, str(resource)))

        search_state = (pat, key)

    if raise_if_missing and (search_state[1] is None):
      raise MissingCsekKeyException(resource)

    return search_state[1]

  def __init__(self, json_string):
    self.state = CsekKeyStore._ParseAndValidate(json_string)


def MaybeLookupKey(csek_keys_or_none, resource):
  if csek_keys_or_none and resource:
    return csek_keys_or_none.LookupKey(resource)

  return None


def MaybeLookupKeys(csek_keys_or_none, resources):
  return [MaybeLookupKey(csek_keys_or_none, r) for r in resources]


def MaybeLookupKeysByUri(csek_keys_or_none, parser, uris):
  return MaybeLookupKeys(
      csek_keys_or_none,
      [(parser.Parse(u) if u else None) for u in uris])
