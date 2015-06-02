# Copyright 2014 Google Inc. All Rights Reserved.

"""List clusters command."""
from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.container.lib import util
from googlecloudsdk.core import properties
from googlecloudsdk.core.util import list_printer


class List(base.Command):
  """List existing clusters for running containers."""

  @staticmethod
  def Args(parser):
    """Register flags for this command.

    Args:
      parser: An argparse.ArgumentParser-like object. It is mocked out in order
          to capture some information, but behaves like an ArgumentParser.
    """
    pass

  def Run(self, args):
    """This is what gets called when the user runs this command.

    Args:
      args: an argparse namespace. All the arguments that were provided to this
        command invocation.

    Returns:
      Some value that we want to have printed later.
    """
    client = self.context['container_client']
    messages = self.context['container_messages']
    resources = self.context['registry']

    # ensure the project is provided
    project_id = properties.VALUES.core.project.Get(required=True)
    zone_id = None
    if args.zone:
      zone_id = resources.Parse(args.zone, collection='compute.zones').zone

    try:
      if zone_id:
        # Zone-filtered list
        req = messages.ContainerProjectsZonesClustersListRequest(
            projectId=project_id, zoneId=zone_id)
        return client.projects_zones_clusters.List(req)
      else:
        # Global list
        req = messages.ContainerProjectsClustersListRequest(
            projectId=project_id)
        return client.projects_clusters.List(req)
    except apitools_base.HttpError as error:
      raise exceptions.HttpException(util.GetError(error))

  def Display(self, args, result):
    """This method is called to print the result of the Run() method.

    Args:
      args: The arguments that command was run with.
      result: The value returned from the Run() method.
    """
    list_printer.PrintResourceList(
        'container.projects.zones.clusters', result.clusters)
