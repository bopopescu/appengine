# Copyright 2014 Google Inc. All Rights Reserved.

"""The command group for the DeploymentManager V2 CLI."""

from googlecloudapis.deploymentmanager import v2beta2 as deploymentmanager_v2beta2
from googlecloudapis.deploymentmanager.v2beta2 import deploymentmanager_v2beta2_messages as v2beta2_messages
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.core import properties
from googlecloudsdk.core.credentials import store


@base.ReleaseTracks(base.ReleaseTrack.BETA)
class DmV2(base.Group):
  """Manage Deployments of cloud resources using version 2 beta of the API."""

  @staticmethod
  def Args(parser):
    """Args is called by calliope to gather arguments for this command.

    Args:
      parser: An argparse parser that you can use to add arguments that go
          on the command line after this command. Positional arguments are
          allowed.
    """
    pass

  @exceptions.RaiseToolExceptionInsteadOf(store.Error)
  def Filter(self, context, args):
    """Context() is a filter function that can update the context.

    Args:
      context: The current context.
      args: The argparse namespace that was specified on the CLI or API.

    Returns:
      The updated context.
    Raises:
      ToolException: When no project is specified.
    """

    # Apitools client to make API requests.
    url = '/'.join([properties.VALUES.core.api_host.Get(), 'deploymentmanager'])

    # v2beta2
    context['deploymentmanager-v2beta2'] = (
        deploymentmanager_v2beta2.DeploymentmanagerV2beta2(
            get_credentials=False, url='/'.join([url, 'v2beta2']),
            http=self.Http())
    )
    context['deploymentmanager-v2beta2-messages'] = v2beta2_messages

    return context
