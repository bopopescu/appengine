# Copyright 2014 Google Inc. All Rights Reserved.
"""Command for deleting URL maps."""
from googlecloudsdk.compute.lib import base_classes


class Delete(base_classes.GlobalDeleter):
  """Delete backend services."""

  @staticmethod
  def Args(parser):
    cli = Delete.GetCLIGenerator()
    base_classes.GlobalDeleter.Args(parser, 'compute.urlMaps', cli,
                                    'compute.url-maps')

  @property
  def service(self):
    return self.compute.urlMaps

  @property
  def resource_type(self):
    return 'urlMaps'


Delete.detailed_help = {
    'brief': 'Delete URL maps',
    'DESCRIPTION': """\
        *{command}* deletes one or more URL maps.
        """,
}
