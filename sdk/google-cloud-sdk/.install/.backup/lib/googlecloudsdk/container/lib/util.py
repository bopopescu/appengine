# Copyright 2014 Google Inc. All Rights Reserved.

"""Common utilities for the containers tool."""
import cStringIO
import json
import os
import time


import distutils.version as dist_version

from googlecloudapis.apitools.base import py as apitools_base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.container.lib import kubeconfig as kconfig
from googlecloudsdk.core import config
from googlecloudsdk.core import log
from googlecloudsdk.core import properties
from googlecloudsdk.core.util import console_io
from googlecloudsdk.core.util import files as file_utils


class Error(Exception):
  """Class for errors raised by container commands."""


class APIHttpError(Error, exceptions.HttpException):
  """Class for Http errors returned from Google API."""

  def __init__(self, code, message):
    super(APIHttpError, self).__init__(message)
    self.code = code
    self.message = message

  def __str__(self):
    return 'ResponseError: code={0}, message={1}'.format(
        self.code, self.message)


def GetError(error):
  """Parse HttpError returned from Google API into printable APIHttpError.

  Args:
    error: apitools_base.HttpError.
  Returns:
    APIHttpError containing http error code and error message.
  """
  data = json.loads(error.content)
  code = int(data['error']['code'])
  message = data['error']['message']
  return APIHttpError(code, message)


def WaitForOperation(operation, project_id, context, message,
                     timeout_s=1200, poll_period_s=5):
  """Poll container Operation until its status is done or timeout reached.

  Args:
    operation: Operation message of the operation to be polled.
    project_id: str, project which owns this operation.
    context: dict, container Command context.
    message: str, message to display to user while polling.
    timeout_s: number, seconds to poll with retries before timing out.
    poll_period_s: number, delay in seconds between requests.

  Returns:
    Operation: the return value of the last successful operations.get
    request.

  Raises:
    Error: if the operation times out or finishes with an error.
  """
  client = context['container_client']
  messages = context['container_messages']

  req = messages.ContainerProjectsZonesOperationsGetRequest(
      operationId=operation.name, projectId=project_id, zoneId=operation.zone)
  with console_io.ProgressTracker(message, autotick=True):
    start_time = time.clock()
    while timeout_s > (time.clock() - start_time):
      try:
        operation = client.projects_zones_operations.Get(req)
        if operation.status == messages.Operation.StatusValueValuesEnum.done:
          # Success!
          log.info('Operation %s succeeded after %.3f seconds',
                   operation, (time.clock() - start_time))
          break
      except apitools_base.HttpError as error:
        log.debug('GetOperation failed: %s', error)
        # Keep trying until we timeout in case error is transient.
      time.sleep(poll_period_s)
  if operation.status != messages.Operation.StatusValueValuesEnum.done:
    log.err.Print('Timed out waiting for operation %s' % operation)
    raise Error(
        'Operation [{0}] is still running'.format(operation))
  if operation.errorMessage:
    raise Error('Operation [{0}] finished with error: {1}'.format(
        operation, operation.errorMessage))

  return operation


def ParseCluster(name, context):
  """Parse cluster using given resources.Registry.

  Args:
    name: str, cluster name or resource url.
    context: container Command context.
  Returns:
    resources.Resource for the cluster.
  """
  resources = context['registry']
  # Ensure the zone and project are provided.
  properties.VALUES.compute.zone.Get(required=True)
  properties.VALUES.core.project.Get(required=True)
  return resources.Parse(name, collection='container.projects.zones.clusters')


def ConstructList(title, items):
  buf = cStringIO.StringIO()
  printer = console_io.ListPrinter(title)
  printer.Print(items, output_stream=buf)
  return buf.getvalue()


def IsLegacyVersion(version):
  """Returns true if given version string represents a pre 0.5+ version.

  Args:
    version: str, Kubernetes version (e.g. "0.4.4" or "0.5.2").

  Returns:
    bool: True, if version string is pre 0.5, else False.
  """

  return dist_version.LooseVersion(version) < dist_version.LooseVersion('0.5')


WRONG_ZONE_ERROR_MSG = """\
{error}
Could not find [{name}] in [{wrong_zone}].
Did you mean [{name}] in [{zone}]?"""
NO_SUCH_CLUSTER_ERROR_MSG = """\
{error}
No cluster named '{name}' in {project}."""


def DescribeCluster(cluster_ref, context):
  """Describe a running cluster.

  Args:
    cluster_ref: cluster Resource to describe.
    context: container Command context.
  Returns:
    Cluster message.
  Raises:
    Error: if cluster cannot be found.
  """
  client = context['container_client']
  messages = context['container_messages']
  try:
    return client.projects_zones_clusters.Get(cluster_ref.Request())
  except apitools_base.HttpError as error:
    api_error = GetError(error)
    if api_error.code != 404:
      raise api_error

  # Cluster couldn't be found, maybe user got zone wrong?
  try:
    req = messages.ContainerProjectsClustersListRequest(
        projectId=cluster_ref.projectId)
    clusters = client.projects_clusters.List(req).clusters
  except apitools_base.HttpError as error:
    raise exceptions.HttpException(GetError(error))
  for cluster in clusters:
    if cluster.name == cluster_ref.clusterId:
      # User likely got zone wrong.
      raise Error(WRONG_ZONE_ERROR_MSG.format(
          error=api_error,
          name=cluster_ref.clusterId,
          wrong_zone=cluster_ref.zoneId,
          zone=cluster.zone))
  # Couldn't find a cluster with that name.
  raise Error(NO_SUCH_CLUSTER_ERROR_MSG.format(
      error=api_error,
      name=cluster_ref.clusterId,
      project=cluster_ref.projectId))


KMASTER_NAME_FORMAT = 'k8s-{cluster_name}-master'
# These are determined by the version of kubernetes the cluster is running.
# This needs kept up to date when validating new cluster api versions.
KMASTER_LEGACY_CERT_DIRECTORY = '/usr/share/nginx'
KMASTER_CERT_DIRECTORY = '/srv/kubernetes'
KMASTER_USER = 'root'  # for /usr/share/...
KMASTER_CLIENT_KEY = 'kubecfg.key'
KMASTER_CLIENT_CERT = 'kubecfg.crt'
KMASTER_CERT_AUTHORITY = 'ca.crt'
KMASTER_CERT_FILES = [KMASTER_CLIENT_KEY, KMASTER_CLIENT_CERT,
                      KMASTER_CERT_AUTHORITY]


def GetKmasterCertDirectory(version):
  """Returns the directory on the Kubernetes master where SSL certs are stored.

  Args:
    version: str, Kubernetes version (e.g. "0.4.4" or "0.5.2").

  Returns:
    str, the path to SSL certs on the Kubernetes master.
  """
  if IsLegacyVersion(version):
    return KMASTER_LEGACY_CERT_DIRECTORY
  return KMASTER_CERT_DIRECTORY


KUBECONFIG_USAGE_FMT = '''\
kubeconfig entry generated for {cluster}. To switch context to the cluster, run

$ kubectl config use-context {context}
'''


class ClusterConfig(object):
  """Encapsulates persistent cluster config data.

  Call ClusterConfig.Load() or ClusterConfig.Persist() to create this
  object.
  """

  _CONFIG_DIR_FORMAT = '{project}_{zone}_{cluster}'

  KUBECONTEXT_FORMAT = 'gke_{project}_{zone}_{cluster}'

  def __init__(self, **kwargs):
    self.cluster_name = kwargs['cluster_name']
    self.zone_id = kwargs['zone_id']
    self.project_id = kwargs['project_id']
    self.server = kwargs['server']
    # auth options are basic (user,password) OR bearer token.
    self.username = kwargs.get('username')
    self.password = kwargs.get('password')
    self.token = kwargs.get('token')
    self._has_certs = kwargs['has_certs']

  def __str__(self):
    return 'ClusterConfig{project:%s, cluster:%s, zone:%s, endpoint:%s}' % (
        self.project_id, self.cluster_name, self.zone_id, self.endpoint)

  def _Fullpath(self, filename):
    return os.path.abspath(os.path.join(self.config_dir, filename))

  @property
  def config_dir(self):
    return ClusterConfig.GetConfigDir(
        self.cluster_name, self.zone_id, self.project_id)

  @property
  def ca_path(self):
    return self._Fullpath(KMASTER_CERT_AUTHORITY)

  @property
  def client_cert_path(self):
    return self._Fullpath(KMASTER_CLIENT_CERT)

  @property
  def client_key_path(self):
    return self._Fullpath(KMASTER_CLIENT_KEY)

  @property
  def kube_context(self):
    return ClusterConfig.KubeContext(
        self.cluster_name, self.zone_id, self.project_id)

  @property
  def has_certs(self):
    return self._has_certs

  @staticmethod
  def GetConfigDir(cluster_name, zone_id, project_id):
    return os.path.join(
        config.Paths().container_config_path,
        ClusterConfig._CONFIG_DIR_FORMAT.format(
            project=project_id, zone=zone_id, cluster=cluster_name))

  @staticmethod
  def KubeContext(cluster_name, zone_id, project_id):
    return ClusterConfig.KUBECONTEXT_FORMAT.format(
        project=project_id, cluster=cluster_name, zone=zone_id)

  def GenKubeconfig(self):
    """Generate kubeconfig for this cluster."""
    context = self.kube_context
    kubeconfig = kconfig.Kubeconfig.Default()
    # Use same key for context, cluster, and user
    kubeconfig.contexts[context] = kconfig.Context(context, context, context)
    ca_path = cert_path = key_path = None
    if self.has_certs:
      ca_path = self.ca_path
      cert_path = self.client_cert_path
      key_path = self.client_key_path
    kubeconfig.clusters[context] = kconfig.Cluster(
        context, self.server, ca_path)
    kwargs = {
        'token': self.token,
        'username': self.username,
        'password': self.password,
        'cert_path': cert_path,
        'key_path': key_path
    }
    kubeconfig.users[context] = kconfig.User(context, **kwargs)
    kubeconfig.SaveToFile()
    path = kconfig.Kubeconfig.DefaultPath()
    log.debug('Saved kubeconfig to %s', path)
    log.status.Print(KUBECONFIG_USAGE_FMT.format(
        cluster=self.cluster_name, context=context))

  @classmethod
  def Persist(cls, cluster, project_id, cli):
    """Save config data for the given cluster.

    Persists config file and kubernetes auth file for the given cluster
    to cloud-sdk config directory and returns ClusterConfig object
    encapsulating the same data.

    Args:
      cluster: valid Cluster message to persist config data for.
      project_id: project that owns this cluster.
      cli: calliope.cli.CLI, The top-level CLI object.
    Returns:
      ClusterConfig of the persisted data.
    """
    config_dir = cls.GetConfigDir(cluster.name, cluster.zone, project_id)
    log.debug('Saving cluster config to %s', config_dir)
    file_utils.MakeDir(config_dir)

    certs = cls._FetchCertFiles(cluster, project_id, cli)
    if not certs:
      log.warn('Failed to get cert files from master. Certificate checking '
               'will be disabled. Run a kubectl command with '
               '--purge-config-cache to try fetching certs again.')

    kwargs = {
        'cluster_name': cluster.name,
        'zone_id': cluster.zone,
        'project_id': project_id,
        'server': 'https://' + cluster.endpoint,
        'has_certs': bool(certs),
    }
    if cluster.masterAuth.bearerToken:
      kwargs['token'] = cluster.masterAuth.bearerToken
    else:
      kwargs['username'] = cluster.masterAuth.user
      kwargs['password'] = cluster.masterAuth.password

    c_config = cls(**kwargs)
    c_config.GenKubeconfig()
    return c_config

  @classmethod
  def Load(cls, cluster_name, zone_id, project_id):
    """Load and verify config for given cluster.

    Args:
      cluster_name: name of cluster to load config for.
      zone_id: compute zone the cluster is running in.
      project_id: project in which the cluster is running.
    Returns:
      ClusterConfig for the cluster, or None if config data is missing or
      incomplete.
    """
    log.debug('Loading cluster config for cluster=%s, zone=%s project=%s',
              cluster_name, zone_id, project_id)
    k = kconfig.Kubeconfig.Default()

    key = cls.KubeContext(cluster_name, zone_id, project_id)

    cluster = k.clusters.get(key) and k.clusters[key].get('cluster')
    user = k.users.get(key) and k.users[key].get('user')
    context = k.contexts.get(key) and k.contexts[key].get('context')
    if not cluster or not user or not context:
      log.debug('missing kubeconfig entries for %s', key)
      return None
    if context.get('user') != key or context.get('cluster') != key:
      log.debug('invalid context %s', context)
      return None

    # Verify cluster data
    server = cluster.get('server')
    insecure = cluster.get('insecure-skip-tls-verify')
    ca_path = cluster.get('certificate-authority')
    if not server:
      log.debug('missing cluster.server entry for %s', key)
      return None
    if insecure and ca_path:
      log.debug('cluster cannot specify both certificate-authority '
                'and insecure-skip-tls-verify')
      return None
    elif not insecure and not ca_path:
      log.debug('cluster must specify either certificate-authority '
                'or insecure-skip-tls-verify')
      return None

    # Verify user data
    username = user.get('username')
    password = user.get('password')
    token = user.get('token')
    cert_path = user.get('client-certificate')
    key_path = user.get('client-key')
    if (not username or not password) and not token:
      log.debug('missing auth info for user %s: %s', key, user)
      return None

    # Verify cert files exist if specified
    for fname in ca_path, cert_path, key_path:
      if fname and not os.path.isfile(fname):
        log.debug('could not find %s', fname)
        return None

    # Construct ClusterConfig
    kwargs = {
        'cluster_name': cluster_name,
        'zone_id': zone_id,
        'project_id': project_id,
        'server': server,
        'username': username,
        'password': password,
        'token': token,
        'has_certs': not insecure,
    }
    return cls(**kwargs)

  @classmethod
  def Purge(cls, cluster_name, zone_id, project_id):
    config_dir = cls.GetConfigDir(cluster_name, zone_id, project_id)
    if os.path.exists(config_dir):
      file_utils.RmTree(config_dir)
    # purge from kubeconfig
    kubeconfig = kconfig.Kubeconfig.Default()
    kubeconfig.Clear(cls.KubeContext(cluster_name, zone_id, project_id))
    kubeconfig.SaveToFile()
    log.debug('Purged cluster config from %s', config_dir)

  @classmethod
  def _FetchCertFiles(cls, cluster, project_id, cli):
    """Call into gcloud.compute.copy_files to copy certs from cluster.

    Copies cert files from Kubernetes master into local config directory
    for the provided cluster.

    Args:
      cluster: a valid Cluster message.
      project_id: str, project that owns this cluster.
      cli: calliope.cli.CLI, The top-level CLI object.
    Returns:
      bool, True if fetch succeeded, else False.
    """
    instance_name = KMASTER_NAME_FORMAT.format(cluster_name=cluster.name)

    cert_dir = GetKmasterCertDirectory(cluster.clusterApiVersion)
    paths = [os.path.join(cert_dir, cert_file) for
             cert_file in KMASTER_CERT_FILES]
    # Put all the paths together in the same CLI argument so that SCP copies all
    # the files in one go rather than separately, to keep the user from being
    # asked for their GCE SSH passphrase multiple times.
    remote_file_paths = '{user}@{instance_name}:{filepaths}'.format(
        user=KMASTER_USER, instance_name=instance_name,
        filepaths=' '.join(paths))

    config_dir = cls.GetConfigDir(cluster.name, cluster.zone, project_id)
    log.out.Print('Using gcloud compute copy-files to fetch ssl certs from '
                  'cluster master...')
    try:
      cli.Execute(['compute', 'copy-files', '--zone=' + cluster.zone,
                   remote_file_paths, config_dir])
      return True
    except exceptions.ToolException as error:
      log.error(
          'Fetching ssl certs from cluster master failed:\n\n%s\n\n'
          'You can still interact with the cluster, but you may see a warning '
          'that certificate checking is disabled.',
          error)
      return False

