# Copyright 2015 Google Inc. All Rights Reserved.
"""Commands for reading and manipulating groups."""

from googlecloudsdk.calliope import base


@base.ReleaseTracks(base.ReleaseTrack.ALPHA)
class Groups(base.Group):
  """Read and manipulate Google Compute Engine groups."""

Groups.detailed_help = {
    'brief': 'Read and manipulate Google Compute Engine groups',
}
