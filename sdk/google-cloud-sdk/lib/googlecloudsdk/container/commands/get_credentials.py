# Copyright 2015 Google Inc. All Rights Reserved.

"""Fetch cluster credentials."""
from googlecloudsdk.calliope import actions
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.container.lib import kubeconfig as kconfig
from googlecloudsdk.container.lib import util
from googlecloudsdk.core import log
from googlecloudsdk.core import properties


class GetCredentials(base.Command):
  """Fetch credentials for a running cluster.

  See https://cloud.google.com/container-engine/docs/kubectl for
  kubectl documentation.
  """

  @staticmethod
  def Args(parser):
    """Register flags for this command.

    Args:
      parser: An argparse.ArgumentParser-like object. It is mocked out in order
          to capture some information, but behaves like an ArgumentParser.
    """
    parser.add_argument(
        '--cluster', '-n',
        help='The name of the cluster to issue commands to.',
        action=actions.StoreProperty(properties.VALUES.container.cluster))

  @exceptions.RaiseToolExceptionInsteadOf(util.Error)
  def Run(self, args):
    """This is what gets called when the user runs this command.

    Args:
      args: an argparse namespace. All the arguments that were provided to this
        command invocation.

    Raises:
      util.Error: if the cluster is unreachable or not running.
    """
    name = properties.VALUES.container.cluster.Get(required=True)
    cluster_ref = util.ParseCluster(name, self.context)

    log.status.Print('Fetching cluster endpoint and auth data.')
    # Call DescribeCluster to get auth info and cache for next time
    cluster = util.DescribeCluster(cluster_ref, self.context)
    messages = self.context['container_messages']
    if cluster.status != messages.Cluster.StatusValueValuesEnum.running:
      raise util.Error('cluster %s is not running' % cluster_ref.clusterId)
    c_config = util.ClusterConfig.Persist(
        cluster, cluster_ref.projectId, self.cli)
    kubeconfig = kconfig.Kubeconfig.Default()
    kubeconfig.SetCurrentContext(c_config.kube_context)
    kubeconfig.SaveToFile()
