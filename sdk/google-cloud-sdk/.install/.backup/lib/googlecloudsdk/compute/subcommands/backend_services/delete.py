# Copyright 2014 Google Inc. All Rights Reserved.
"""Command for deleting backend services."""
from googlecloudsdk.compute.lib import base_classes


class Delete(base_classes.GlobalDeleter):
  """Delete backend services."""

  @staticmethod
  def Args(parser):
    cli = Delete.GetCLIGenerator()
    base_classes.GlobalDeleter.Args(parser, 'compute.backendServices', cli,
                                    'compute.backend-services')

  @property
  def service(self):
    return self.compute.backendServices

  @property
  def resource_type(self):
    return 'backendServices'


Delete.detailed_help = {
    'brief': 'Delete backend services',
    'DESCRIPTION': """\
        *{command}* deletes one or more backend services.
        """,
}
