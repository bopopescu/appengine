# Copyright 2014 Google Inc. All Rights Reserved.

"""Create cluster command."""
import collections
import random
import string

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import arg_parsers
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.compute.lib import constants
from googlecloudsdk.container.lib import kubeconfig as kconfig
from googlecloudsdk.container.lib import util
from googlecloudsdk.core import log
from googlecloudsdk.core.util import list_printer


class Create(base.Command):
  """Create a cluster for running containers."""

  @staticmethod
  def Args(parser):
    """Register flags for this command.

    Args:
      parser: An argparse.ArgumentParser-like object. It is mocked out in order
          to capture some information, but behaves like an ArgumentParser.
    """
    parser.add_argument('name', help='The name of this cluster.')
    parser.add_argument(
        '--no-wait',
        dest='wait',
        action='store_false',
        help='Return after issuing create request without polling the operation'
        ' for completion.')
    parser.add_argument(
        '--num-nodes',
        type=int,
        help='The number of nodes in the cluster.',
        default=3)
    parser.add_argument(
        '--machine-type', '-m',
        help='The type of machine to use for workers. Defaults to '
        'server-specified')
    parser.add_argument(
        '--source-image',
        help='The source image to use for workers. Defaults to '
        'server-specified')
    parser.add_argument(
        '--network',
        help='The Compute Engine Network that the cluster will connect to. '
        'Google Container Engine will use this network when creating routes '
        'and firewalls for the clusters. Defaults to the \'default\' network.')
    parser.add_argument(
        '--container-ipv4-cidr',
        help='The IP addresses of the container pods in this cluster in CIDR '
        'notation (e.g. 10.0.0.0/14). Defaults to server-specified')
    parser.add_argument(
        '--user', '-u',
        help='The user name to use for cluster auth.',
        default='admin')
    parser.add_argument(
        '--password',
        help='The password to use for cluster auth. Defaults to a '
        'randomly-generated string.')
    parser.add_argument(
        '--cluster-api-version',
        help='The kubernetes release version to launch the cluster with. '
        'Defaults to server-specified.')
    parser.add_argument(
        '--no-enable-cloud-logging',
        help='Don\'t automatically send logs from the cluster to the '
        'Google Cloud Logging API.',
        dest='enable_cloud_logging',
        action='store_false')
    parser.set_defaults(enable_cloud_logging=True)
    parser.add_argument(
        '--scopes',
        type=arg_parsers.ArgList(min_length=1),
        metavar='[ACCOUNT=]SCOPE',
        action=arg_parsers.FloatingListValuesCatcher(),
        help="""\
Specifies service accounts and scopes for the node instances.
Service accounts generate access tokens that can be accessed
through each instance's metadata server and used to authenticate
applications on the instance. The account can be either an email
address or an alias corresponding to a service account. If
account is omitted, the project's default service account is used.
The default service account can be specified explicitly using
the alias ``default''.
Examples:

  $ {{command}} example-cluster --scopes bigquery,me@project.gserviceaccount.com=storage-rw

  $ {{command}} example-cluster --scopes bigquery storage-rw compute-ro

Multiple [ACCOUNT=]SCOPE pairs can specified, separated by commas.
The scopes specified will be added onto the scopes necessary
for the cluster to function properly, which are always put
in the default service account.

SCOPE can be either the full URI of the scope or an alias.
Available aliases are:

Alias,URI
{aliases}
""".format(
    aliases='\n        '.join(
        ','.join(value) for value in
        sorted(constants.SCOPES.iteritems()))))

  @exceptions.RaiseToolExceptionInsteadOf(util.Error)
  def Run(self, args):
    """This is what gets called when the user runs this command.

    Args:
      args: an argparse namespace. All the arguments that were provided to this
        command invocation.

    Returns:
      Cluster message for the successfully created cluster.

    Raises:
      ToolException, if creation failed.
    """
    client = self.context['container_client']
    messages = self.context['container_messages']
    cluster_ref = util.ParseCluster(args.name, self.context)

    if args.password:
      password = args.password
    else:
      password = ''.join(random.SystemRandom().choice(
          string.ascii_letters + string.digits) for _ in range(16))

    node_config = messages.NodeConfig()
    if args.machine_type:
      node_config.machineType = args.machine_type
    if args.source_image:
      node_config.sourceImage = args.source_image
    node_config.serviceAccounts = self.CreateServiceAccountMessages(args,
                                                                    messages)

    create_cluster_req = messages.CreateClusterRequest(
        cluster=messages.Cluster(
            name=cluster_ref.clusterId,
            numNodes=args.num_nodes,
            nodeConfig=node_config,
            masterAuth=messages.MasterAuth(user=args.user,
                                           password=password),
            enableCloudLogging=args.enable_cloud_logging))
    if args.cluster_api_version:
      create_cluster_req.cluster.clusterApiVersion = args.cluster_api_version
    if args.network:
      create_cluster_req.cluster.network = args.network
    if args.container_ipv4_cidr:
      create_cluster_req.cluster.containerIpv4Cidr = args.container_ipv4_cidr

    req = messages.ContainerProjectsZonesClustersCreateRequest(
        createClusterRequest=create_cluster_req,
        projectId=cluster_ref.projectId,
        zoneId=cluster_ref.zoneId)

    cluster = None
    try:
      operation = client.projects_zones_clusters.Create(req)

      if not args.wait:
        return util.DescribeCluster(cluster_ref, self.context)

      operation = util.WaitForOperation(
          operation, cluster_ref.projectId, self.context,
          'Creating cluster {0}'.format(cluster_ref.clusterId))

      # Get Cluster
      cluster = util.DescribeCluster(cluster_ref, self.context)
    except apitools_base.HttpError as error:
      raise exceptions.HttpException(util.GetError(error))

    log.CreatedResource(cluster_ref)
    # Persist cluster config
    c_config = util.ClusterConfig.Persist(
        cluster, cluster_ref.projectId, self.cli)
    if c_config:
      if not c_config.has_certs:
        # Purge config so we retry the cert fetch on next kubectl command
        util.ClusterConfig.Purge(
            cluster.name, cluster.zone, cluster_ref.projectId)
        # Exit with non-success returncode if certs could not be fetched
        self.exit_code = 1
      else:
        # Set current-context to new cluster if one is not already set
        kubeconfig = kconfig.Kubeconfig.Default()
        if not kubeconfig.current_context:
          kubeconfig.SetCurrentContext(c_config.kube_context)
          kubeconfig.SaveToFile()

    return cluster

  def Display(self, args, result):
    """This method is called to print the result of the Run() method.

    Args:
      args: The arguments that command was run with.
      result: The value returned from the Run() method.
    """
    list_printer.PrintResourceList(
        'container.projects.zones.clusters', [result])

  @exceptions.RaiseToolExceptionInsteadOf(util.Error)
  def CreateServiceAccountMessages(self, args, messages):
    """This method converts from the --scopes flag to a list of ServiceAccounts.

    Args:
      args: The arguments that the command was run with.
      messages: The container API's protocol buffer message types.

    Returns:
      A list of ServiceAccount messages corresponding to --scopes.
    """
    if not args.scopes:
      return []

    accounts_to_scopes = collections.defaultdict(list)
    for scope in args.scopes:
      parts = scope.split('=')
      if len(parts) == 1:
        account = 'default'
        scope_uri = scope
      elif len(parts) == 2:
        account, scope_uri = parts
      else:
        raise exceptions.ToolException(
            '[{0}] is an illegal value for [--scopes]. Values must be of the '
            'form [SCOPE] or [ACCOUNT=SCOPE].'.format(scope))

      # Expand any scope aliases (like 'storage-rw') that the user provided
      # to their official URL representation.
      scope_uri = constants.SCOPES.get(scope_uri, scope_uri)
      accounts_to_scopes[account].append(scope_uri)

    accounts = []
    for account, scopes in sorted(accounts_to_scopes.iteritems()):
      accounts.append(messages.ServiceAccount(
          email=account,
          scopes=sorted(scopes)))
    return accounts
