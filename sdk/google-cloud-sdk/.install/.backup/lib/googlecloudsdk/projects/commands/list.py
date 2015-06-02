# Copyright 2014 Google Inc. All Rights Reserved.
"""Command to list all Project IDs associated with the active user."""

import textwrap

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudapis.apitools.base.py import exceptions
from googlecloudsdk.calliope import base
from googlecloudsdk.core.util import list_printer
from googlecloudsdk.projects.lib import util


class List(base.Command):
  """List the Projects for the active user's credentials."""

  detailed_help = {
      'brief': 'List all active Projects.',
      'DESCRIPTION': textwrap.dedent("""\
          This commands lists all active Projects (ID and title), for the active
          user's credentials, in alphabetical order by Project title.
          Projects which have been deleted or are pending deletion will not be
          included.

          You can specify the maximum number of Projects to list with the
          'limit' flag.
      """),
      'EXAMPLES': textwrap.dedent("""\
          The following command will list a maximum of 5 Projects, out of all
          of the active user's active Projects, sorted alphabetically by title.
            $ gcloud projects list --limit=5
      """),
  }

  @staticmethod
  def Args(parser):
    parser.add_argument('--limit', default=None, type=int,
                        help='Maximum number of results.')

  def Run(self, args):
    """"Run the list command."""

    projects = self.context['projects_client']
    messages = self.context['projects_messages']
    try:
      for project in apitools_base.YieldFromList(
          projects.projects,
          messages.CloudresourcemanagerProjectsListRequest(),
          limit=args.limit,
          field='projects',
          predicate=util.IsActive,
          batch_size_attribute='pageSize'):
        yield project
    except exceptions.HttpError as error:
      raise util.GetError(error)

  def Display(self, args, result):
    list_printer.PrintResourceList('cloudresourcemanager.projects', result)
