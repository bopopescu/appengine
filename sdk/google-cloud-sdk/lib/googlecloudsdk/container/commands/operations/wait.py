# Copyright 2015 Google Inc. All Rights Reserved.

"""Wait operations command."""
from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.container.lib import util
from googlecloudsdk.core import properties


class Wait(base.Command):
  """Poll an operation for completion."""

  @staticmethod
  def Args(parser):
    """Register flags for this command.

    Args:
      parser: An argparse.ArgumentParser-like object. It is mocked out in order
          to capture some information, but behaves like an ArgumentParser.
    """
    parser.add_argument('operation_id', help='The operation id to poll.')

  @exceptions.RaiseToolExceptionInsteadOf(util.Error)
  def Run(self, args):
    """This is what gets called when the user runs this command.

    Args:
      args: an argparse namespace. All the arguments that were provided to this
        command invocation.

    Returns:
      Some value that we want to have printed later.
    """
    client = self.context['container_client']
    resources = self.context['registry']

    properties.VALUES.compute.zone.Get(required=True)
    properties.VALUES.core.project.Get(required=True)
    operation_ref = resources.Parse(
        args.operation_id,
        collection='container.projects.zones.operations')

    try:
      operation = client.projects_zones_operations.Get(operation_ref.Request())
      return util.WaitForOperation(
          operation, operation_ref.projectId, self.context,
          'Waiting for {0} to complete'.format(operation_ref.operationId))
    except apitools_base.HttpError as error:
      raise exceptions.HttpException(util.GetError(error))

  def Display(self, args, result):
    """This method is called to print the result of the Run() method.

    Args:
      args: The arguments that command was run with.
      result: The value returned from the Run() method.
    """
    self.format(result)
