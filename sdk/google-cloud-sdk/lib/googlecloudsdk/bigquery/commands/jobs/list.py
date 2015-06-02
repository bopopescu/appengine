# Copyright 2015 Google Inc. All Rights Reserved.

"""Implementation of gcloud bigquery jobs list.
"""

from googlecloudsdk.bigquery.lib import bigquery
from googlecloudsdk.bigquery.lib import job_display
from googlecloudsdk.calliope import base
from googlecloudsdk.core import properties
from googlecloudsdk.core.util import list_printer


class JobsList(base.Command):
  """Lists all jobs in a particular project.

  By default, jobs in the current project are listed; this can be overridden
  with the gcloud --project flag. The job ID, job type, state, start time, and
  duration of all jobs in the project are listed.
  """

  @staticmethod
  def Args(parser):
    """Register flags for this command."""
    pass

  def Run(self, args):
    """This is what gets called when the user runs this command.

    Args:
      args: an argparse namespeace, All the arguments that were provided to this
        command invocation.

    Returns:
      an iterator over JobsValueListEntry messages
    """
    project = bigquery.Project(
        properties.VALUES.core.project.Get(required=True))
    return project.GetCurrentRawJobsListGenerator()

  def Display(self, args, jobs):
    """This method is called to print the result of the Run() method.

    Args:
      args: The arguments that command was run with.
      jobs: The iterator over JobsValueListEntry messages returned from the
        Run()
        method.
    """
    list_printer.PrintResourceList(
        'bigquery.jobs.list',
        [job_display.DisplayInfo(entry) for entry in jobs])
