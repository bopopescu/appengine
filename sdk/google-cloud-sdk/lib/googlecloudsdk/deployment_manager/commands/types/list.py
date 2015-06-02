# Copyright 2014 Google Inc. All Rights Reserved.

"""operations list command."""

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.core import log
from googlecloudsdk.core import properties
from googlecloudsdk.deployment_manager.lib import dm_v2_util


class List(base.Command):
  """List types in a project.

  Prints a a list of the available resource types.
  """

  detailed_help = {
      'DESCRIPTION': '{description}',
      'EXAMPLES': """\
          To print out a list of all available type names, run:

            $ {command}
          """,
  }

  def Run(self, args):
    """Run 'types list'.

    Args:
      args: argparse.Namespace, The arguments that this command was invoked
          with.

    Returns:
      The list of types for this project.

    Raises:
      HttpException: An http error response was received while executing api
          request.
    """
    client = self.context['deploymentmanager-v2beta2']
    messages = self.context['deploymentmanager-v2beta2-messages']
    project = properties.VALUES.core.project.Get(required=True)

    try:
      response = client.types.List(
          messages.DeploymentmanagerTypesListRequest(
              project=project,
          )
      )
      if response.types:
        return response.types
      else:  # No types found
        return []
    except apitools_base.HttpError as error:
      raise exceptions.HttpException(dm_v2_util.GetError(error))

  def Display(self, args, result):
    """Display prints information about what just happened to stdout.

    Args:
      args: The same as the args in Run.

      result: a list of types, where each dict is a Type object with a name
          attribute.

    Raises:
      ValueError: if result is None or not a list
    """
    if not isinstance(result, list):
      raise ValueError('result must be a list')

    if not result:
      log.Print('No types were found for your project!')
      return

    for type_item in result:
      log.Print(type_item.name)
