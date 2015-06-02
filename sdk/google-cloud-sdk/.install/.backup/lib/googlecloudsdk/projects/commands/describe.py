# Copyright 2014 Google Inc. All Rights Reserved.

"""Command to show metadata for a specified project."""

import textwrap

from googlecloudapis.apitools.base.py import exceptions
from googlecloudsdk.calliope import base
from googlecloudsdk.projects.lib import util


class Describe(base.Command):
  """Show metadata for a Project."""

  detailed_help = {
      'brief': 'Show metadata for a Project.',
      'DESCRIPTION': textwrap.dedent("""\
          This command shows metadata for a Project, given a valid Project ID.

          This call can fail for the following reasons:
              * The project specified does not exist.
              * The active user does not have permission to access the given
                project.
    """),
      'EXAMPLES': textwrap.dedent("""\
          The following command will print metadata for a Project with
          identifier ``FOO-BAR-123''
            $ gcloud projects describe FOO-BAR-123
    """),
  }

  @staticmethod
  def Args(parser):
    parser.add_argument('id', help='Project ID')

  def Run(self, args):
    projects = self.context['projects_client']
    resources = self.context['projects_resources']
    try:
      project_ref = resources.Parse(args.id,
                                    collection='cloudresourcemanager.projects')
      return projects.projects.Get(project_ref.Request())
    except exceptions.HttpError as error:
      raise util.GetError(error)

  def Display(self, args, result):
    """This method is called to print the result of the Run() method.

    Args:
      args: The arguments that command was run with.
      result: The value returned from the Run() method.
    """
    # pylint:disable=not-callable, self.format is callable.
    self.format(result)
# TODO(user): lead the people back to this:
#       util.PrintAlignedColumns(log.out, [
#           ('Title:', result.title),
#           ('Project ID:', result.projectId),
#           ('Project #:', str(result.projectNumber)),
#           ('State:', str(util.GetLifecycle(result))),
#           ('Created:', str(util.MsToDate(result.createdMs)))])
