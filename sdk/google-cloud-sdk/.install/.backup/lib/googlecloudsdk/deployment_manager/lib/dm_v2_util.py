# Copyright 2014 Google Inc. All Rights Reserved.

"""Common helper methods for DeploymentManager V2 Deployments."""

import json
import os
import sys
import time
import yaml

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.calliope.exceptions import HttpException
from googlecloudsdk.core import log
from googlecloudsdk.core.util import console_io
from googlecloudsdk.core.util import resource_printer
from googlecloudsdk.deployment_manager.lib.exceptions import DeploymentManagerError


def PrettyPrint(resource, print_format='json'):
  """Prints the given resource."""
  resource_printer.Print(
      resources=[resource],
      print_format=print_format,
      out=log.out)


def GetError(error, verbose=False):
  """Returns a ready-to-print string representation from the http response.

  Args:
    error: A string representing the raw json of the Http error response.
    verbose: Whether or not to print verbose messages [default false]

  Returns:
    A ready-to-print string representation of the error.
  """
  data = json.loads(error.content)
  if verbose:
    PrettyPrint(data)
  code = data['error']['code']
  message = data['error']['message']
  return 'ResponseError: code={0}, message={1}'.format(code, message)


def SanitizeLimitFlag(limit):
  """Sanitizes and returns a limit flag value.

  Args:
    limit: the limit flag value to sanitize.
  Returns:
    Sanitized limit flag value.
  Raises:
    DeploymentManagerError: if the provided limit flag value is not a positive
        integer.
  """
  if limit is None:
    limit = sys.maxint
  else:
    if limit > sys.maxint:
      limit = sys.maxint
    elif limit <= 0:
      raise DeploymentManagerError(
          '--limit must be a positive integer; received: {0}'
          .format(limit))
  return limit


def WaitForOperation(operation_name, project, context, operation_description,
                     timeout=None):
  """Wait for an operation to complete.

  Polls the operation requested approximately every second, showing a
  progress indicator. Returns when the operation has completed.

  Args:
    operation_name: The name of the operation to wait on, as returned by
        operations.list.
    project: The name of the project that this operation belongs to.
    context: Context object with messages and client to access the
        deploymentmanager service.
    operation_description: A short description of the operation to wait on,
        such as 'create' or 'delete'. Will be displayed to the user.
    timeout: Optional (approximate) timeout in seconds, after which wait
        will return failure.

  Raises:
      HttpException: A http error response was received while executing api
          request. Will be raised if the operation cannot be found.
      DeploymentManagerError: The operation finished with error(s) or exceeded
          the timeout without completing.
  """
  client = context['deploymentmanager-v2beta2']
  messages = context['deploymentmanager-v2beta2-messages']
  ticks = 0
  message = ('Waiting for '
             + ('{0} '.format(operation_description)
                if operation_description else '')
             + operation_name)
  with console_io.ProgressTracker(message, autotick=False) as ticker:
    while timeout is None or ticks < timeout:
      ticks += 1

      try:
        operation = client.operations.Get(
            messages.DeploymentmanagerOperationsGetRequest(
                project=project,
                operation=operation_name,
            )
        )
      except apitools_base.HttpError as error:
        raise HttpException(GetError(error))
      ticker.Tick()
      # Operation status will be one of PENDING, RUNNING, DONE
      if operation.status == 'DONE':
        if operation.error:
          raise DeploymentManagerError(
              'Error in Operation ' + operation_name + ': '
              + str(operation.error))
        else:  # Operation succeeded
          return
      time.sleep(1)  # wait one second and try again
    # Timeout exceeded
    raise DeploymentManagerError(
        'Wait for Operation ' + operation_name + ' exceeded timeout.')


def PrintTable(header, resource_list):
  """Print a table of results with the specified columns.

  Prints a table whose columns are the proto fields specified in the
  header list. Any fields which cannot be found are printed as empty.

  Args:
    header: A list of strings which are the field names to include in the
        table. Must match field names in the resource_list items.
    resource_list: A list of resource objects, each corresponding to a row
        in the table to print.
  """
  printer = resource_printer.TablePrinter(out=log.out)
  printer.AddRow(header)
  for resource in resource_list:
    printer.AddRow([resource[column] if column in resource else ''
                    for column in header])
  printer.Print()


def CreateImport(messages, import_item, base_path):
  """Construct an ImportFile from the provided import file name.

  Args:
    messages: Object with v2beta2 API messages.
    import_item: Item in the config yaml file with a required path attribute
        and optional name attribute.
    base_path: The path to the directory in which the config file resides.

  Returns:
    ImportFile containing the name and content of the import.

  Raises:
    BadFileException: if the import file cannot be read from the specified
        location or if the import does not have a 'path' attribute.
  """
  if 'path' not in import_item:
    raise exceptions.BadFileException('Missing required field path in import')
  import_path = import_item['path']
  import_name = import_item['name'] if 'name' in import_item else import_path
  full_name = os.path.normpath(os.path.join(base_path, import_path))
  # Attempt to read the import contents.
  try:
    with open(full_name, 'r') as file_contents:
      return messages.ImportFile(
          name=import_name,
          content=file_contents.read()
      )
  except IOError:
    raise exceptions.BadFileException('Unable to import file ' + full_name)


def BuildTargetConfig(messages, filename):
  """Construct a TargetConfig from the provided config file with imports.

  Args:
    messages: Object with v2beta2 API messages.
    filename: Name of the config yaml file, with an optional list of imports.

  Returns:
    TargetConfig containing the contents of the config file and the names and
    contents of any imports.

  Raises:
    BadFileException: if the config file or import files cannot be read from
        the specified locations.
  """
  # Read config contents
  try:
    with open(filename, 'r') as config_file:
      config_contents = config_file.read()
    yaml_config = yaml.safe_load(config_contents)
    imports = []
    if 'imports' in yaml_config:
      imports = yaml_config['imports']
  except (IOError, yaml.YAMLError):
    raise exceptions.BadFileException('Unable to read config file ' + filename)
  base_path = os.path.dirname(config_file.name)
  return messages.TargetConfiguration(
      config=config_contents,
      imports=[CreateImport(messages, import_item, base_path)
               for import_item in imports],
  )
