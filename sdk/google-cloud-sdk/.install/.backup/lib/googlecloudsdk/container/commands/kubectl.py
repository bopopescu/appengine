# Copyright 2014 Google Inc. All Rights Reserved.

"""Passthrough command for calling kubectl from gcloud."""
import argparse

from googlecloudsdk.calliope import actions
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.container.lib import kubeconfig as kconfig
from googlecloudsdk.container.lib import util
from googlecloudsdk.core import log
from googlecloudsdk.core import properties
from googlecloudsdk.core.util import platforms
from googlecloudsdk.core.util.compat26 import subprocess


KUBECTL_TIMEOUT_ERR = 'connection timed out'
KUBECTL_TLS_ERR = 'certificate signed by unknown authority'


def WhichKubectl():
  try:
    return subprocess.check_output(['which', 'kubectl'])
  except subprocess.CalledProcessError:
    return None


DEPRECATION_WARNING = '''\
This command is deprecated. Use kubectl directly with the cluster.
{use_context}
kubectl {args}
'''


class Kubectl(base.Command):
  """Pass-through command to call kubectl with arbitrary arguments.

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
        '--purge-config-cache',
        help='Clear cached config data for the cluster. If set, will call '
        '\'container clusters describe\' directly to get cluster data before '
        'executing kubernetes client command.',
        action='store_true')
    parser.add_argument(
        '--cluster', '-n',
        help='The name of the cluster to issue commands to.',
        action=actions.StoreProperty(properties.VALUES.container.cluster))
    parser.add_argument(
        'kubectl_args',
        nargs=argparse.REMAINDER,
        help='Arbitrary arguments to pass to kubectl')

  def LoadClusterConfig(self, args):
    """Load and return ClusterConfig prior to calling a kubectl command.

    Args:
      args: an argparse namespace. All the arguments that were provided to this
        command invocation.

    Returns:
      ClusterConfig for the project,zone,cluster specified by args/properties.

    Raises:
      util.Error: if container API reports cluster is not running.
    """
    name = properties.VALUES.container.cluster.Get(required=True)
    cluster_ref = util.ParseCluster(name, self.context)

    c_config = util.ClusterConfig.Load(
        cluster_ref.clusterId, cluster_ref.zoneId, cluster_ref.projectId)
    if args.purge_config_cache:
      util.ClusterConfig.Purge(
          cluster_ref.clusterId, cluster_ref.zoneId, cluster_ref.projectId)
      c_config = None

    if not c_config or not c_config.has_certs:
      log.status.Print('Fetching cluster endpoint and auth data.')
      # Call DescribeCluster to get auth info and cache for next time
      cluster = util.DescribeCluster(cluster_ref, self.context)
      messages = self.context['container_messages']
      if cluster.status != messages.Cluster.StatusValueValuesEnum.running:
        raise util.Error('cluster %s is not running' % cluster_ref.clusterId)
      c_config = util.ClusterConfig.Persist(
          cluster, cluster_ref.projectId, self.cli)
    return c_config

  def CallKubectl(self, c_config, kubectl_args):
    """Shell out to call to kubectl tool.

    Args:
      c_config: ClusterConfig object for cluster.
      kubectl_args: specific args to call kubectl with (not including args
        for authentication).
    Returns:
      (output, error), where
        output: str, raw output of the kubectl command.
        error: subprocess.CalledProcessError, if the command exited with
          non-zero status, None if command exited with success.
    """
    base_args = [
        '--kubeconfig=%s' % kconfig.Kubeconfig.DefaultPath(),
        '--context=%s' % c_config.kube_context,
    ]
    if not c_config.has_certs:
      log.warn('No certificate files found in %s. Certificate checking '
               'disabled for calls to cluster master.', c_config.config_dir)
    args = ['kubectl'] + base_args + kubectl_args
    try:
      log.debug('Calling \'%s\'', repr(args))
      output = subprocess.check_output(args, stderr=subprocess.STDOUT)
      return (output, None)
    except subprocess.CalledProcessError as error:
      return (error.output, error)

  @exceptions.RaiseToolExceptionInsteadOf(util.Error)
  def Run(self, args):
    """This is what gets called when the user runs this command.

    Args:
      args: an argparse namespace. All the arguments that were provided to this
        command invocation.

    Returns:
      (output, error), where
        output: str, raw output of the kubectl command.
        error: subprocess.CalledProcessError, if the command exited with
          non-zero status, None if command exited with success.

    Raises:
      util.Error: if the current platform is not supported by kubectl.
    """
    local = platforms.Platform.Current()
    if local.operating_system == platforms.OperatingSystem.WINDOWS:
      raise util.Error(
          'This command requires the kubernetes client (kubectl), which is '
          'not available for Windows at this time.')
    if not WhichKubectl():
      raise util.Error(
          'This command requires the kubernetes client (kubectl), which is '
          'installed with the default gcloud components. Run '
          '\'gcloud components update\', or make sure kubectl is '
          'installed somewhere on your path.')

    cluster_config = self.LoadClusterConfig(args)
    # Print deprecation warning, including command to switch context, if needed
    kubeconfig = kconfig.Kubeconfig.Default()
    use_context = ''
    if kubeconfig.current_context != cluster_config.kube_context:
      use_context = '\nkubectl config use-context '+cluster_config.kube_context
    log.warn(DEPRECATION_WARNING.format(
        use_context=use_context, args=' '.join(args.kubectl_args)))

    output, error = self.CallKubectl(cluster_config, args.kubectl_args)
    # If error looks like stale config, try refetching cluster config
    if error and (KUBECTL_TLS_ERR in output or
                  KUBECTL_TIMEOUT_ERR in output):
      log.warn(
          'Command failed with error: %s. Purging config cache and retrying'
          % error.output)
      args.purge_config_cache = True
      cluster_config = self.LoadClusterConfig(args)
      output, error = self.CallKubectl(cluster_config, args.kubectl_args)
    return output, error

  def Display(self, args, result):
    """This method is called to print the result of the CallKubectl method.

    Args:
      args: The arguments that command was run with.
      result: The value returned from the CallKubectl method.
    """
    output, error = result
    if error:
      log.debug('kubectl command %s returned non-zero exit status %d',
                error.cmd, error.returncode)
      log.error(output)
      self.exit_code = error.returncode
    else:
      log.out.Print(output)

Kubectl.detailed_help = {
    'brief': 'Call kubectl with arbitrary arguments.',
    'DESCRIPTION': """\
        Passes given arguments to kubectl along with arguments
        to set the cluster context (overwriting yourself is not recommended).
        Requires the compute/zone and container/cluster properties
        be defined.  If they are missing, the command will fail with an error
        message that describes how to set the missing property.

        WARNING: this command is deprecated! You can run kubectl directly
        after calling

        $ gcloud alpha container get-credentials

        You can then use

        $ kubectl config use-context {context}

        to switch between clusters.
        """.format(
            context=util.ClusterConfig.KUBECONTEXT_FORMAT.format(
                project='PROJECT', zone='ZONE', cluster='CLUSTER'))
}

