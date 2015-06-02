# Copyright 2014 Google Inc. All Rights Reserved.

"""manifests list command."""

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.core import log
from googlecloudsdk.core import properties
from googlecloudsdk.deployment_manager.lib import dm_v2_util


class List(base.Command):
  """List manifests in a deployment.

  Prints a table with summary information on all manifests in the deployment.
  """

  detailed_help = {
      'DESCRIPTION': '{description}',
      'EXAMPLES': """\
          To print out a list of manifests in a deployment, run:

            $ {command} --deployment my-deployment

          To print only the name of each manifest, run:

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

  def Run(self, args):
    """Run 'manifests list'.

    Args:
      args: argparse.Namespace, The arguments that this command was invoked
          with.

    Returns:
      The list of manifests for the specified deployment.

    Raises:
      HttpException: An http error response was received while executing api
          request.
    """
    client = self.context['deploymentmanager-v2beta2']
    messages = self.context['deploymentmanager-v2beta2-messages']
    project = properties.VALUES.core.project.Get(required=True)

    if args.limit:
      limit = dm_v2_util.SanitizeLimitFlag(args.limit)
      request = messages.DeploymentmanagerManifestsListRequest(
          project=project,
          deployment=args.deployment,
          maxResults=limit,
      )
    else:
      request = messages.DeploymentmanagerManifestsListRequest(
          project=project,
          deployment=args.deployment,
      )
    # TODO(user): Pagination (b/17687147).
    try:
      response = client.manifests.List(request)
      if response.manifests:
        results = response.manifests
        if args.limit and len(results) > limit:
          results = results[0:limit]
        return results
      else:  # No manifests found
        return []
    except apitools_base.HttpError as error:
      raise exceptions.HttpException(dm_v2_util.GetError(error))

  def Display(self, unused_args, result):
    """Display prints information about what just happened to stdout.

    Args:
      unused_args: The same as the args in Run.

      result: a list of Manifests, where each dict has a name attribute set.

    Raises:
      ValueError: if result is None or not a list
    """
    if not isinstance(result, list):
      raise ValueError('result must be a list')

    if not result:
      log.Print('No Manifests were found in your deployment!')
      return

    for manifest in result:
      log.Print(manifest.name)
