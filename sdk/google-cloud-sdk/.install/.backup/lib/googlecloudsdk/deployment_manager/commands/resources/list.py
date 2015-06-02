# Copyright 2014 Google Inc. All Rights Reserved.

"""resources list command."""

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.core import log
from googlecloudsdk.core import properties
from googlecloudsdk.core.util import list_printer
from googlecloudsdk.deployment_manager.lib import dm_v2_util


class List(base.Command):
  """List resources in a deployment.

  Prints a table with summary information on all resources in the deployment.
  """

  detailed_help = {
      'DESCRIPTION': '{description}',
      'EXAMPLES': """\
          To print out a list of resources in the deployment with some summary information about each, run:

            $ {command} --deployment my-deployment

          To print only the name of each resource, run:

            $ {command} --deployment my-deployment --simple-list
          """,
  }

  @staticmethod
  def Args(parser):
    """Args is called by calliope to gather arguments for this command.

    Args:
      parser: An argparse parser that you can use to add arguments that go
          on the command line after this command. Positional arguments are
          allowed.
    """
    parser.add_argument('--limit', type=int,
                        help='The maximum number of results to list.')
    parser.add_argument(
        '--simple-list',
        action='store_true',
        default=False,
        help='If true, only the list of resource IDs is printed. If false, '
        'prints a human-readable table of resource information.')

  def Run(self, args):
    """Run 'resources list'.

    Args:
      args: argparse.Namespace, The arguments that this command was invoked
          with.

    Returns:
      The list of resources for the specified deployment.

    Raises:
      HttpException: An http error response was received while executing api
          request.
    """
    client = self.context['deploymentmanager-v2beta2']
    messages = self.context['deploymentmanager-v2beta2-messages']
    project = properties.VALUES.core.project.Get(required=True)

    if args.limit:
      limit = dm_v2_util.SanitizeLimitFlag(args.limit)
      request = messages.DeploymentmanagerResourcesListRequest(
          project=project,
          deployment=args.deployment,
          maxResults=limit)
    else:
      request = messages.DeploymentmanagerResourcesListRequest(
          project=project,
          deployment=args.deployment
      )
    # TODO(user): Pagination (b/17687147).
    try:
      response = client.resources.List(request)
      if response.resources:
        results = response.resources
        if args.limit and len(results) > limit:
          results = results[0:limit]
        return results
      else:
        # No resources to list
        return []
    except apitools_base.HttpError as error:
      raise exceptions.HttpException(dm_v2_util.GetError(error))

  def Display(self, args, result):
    """Display prints information about what just happened to stdout.

    Args:
      args: The same as the args in Run.

      result: a list of Resource objects.

    Raises:
      ValueError: if result is None or not a list
    """
    if not isinstance(result, list):
      raise ValueError('result must be a list')

    if not result:
      log.Print('No Resources were found in your deployment!')
      return

    if args.simple_list:
      for resource in result:
        log.Print(resource.name)
    else:
      list_printer.PrintResourceList('deploymentmanagerv2beta2.resources',
                                     result)
