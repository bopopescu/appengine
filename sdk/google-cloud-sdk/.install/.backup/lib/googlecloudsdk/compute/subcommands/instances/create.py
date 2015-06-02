# Copyright 2014 Google Inc. All Rights Reserved.
"""Command for creating instances."""
import collections
import re

from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import exceptions
from googlecloudsdk.compute.lib import addresses_utils
from googlecloudsdk.compute.lib import base_classes
from googlecloudsdk.compute.lib import constants
from googlecloudsdk.compute.lib import csek_utils
from googlecloudsdk.compute.lib import image_utils
from googlecloudsdk.compute.lib import instance_utils
from googlecloudsdk.compute.lib import metadata_utils
from googlecloudsdk.compute.lib import request_helper
from googlecloudsdk.compute.lib import utils
from googlecloudsdk.compute.lib import windows_password
from googlecloudsdk.compute.lib import zone_utils
from googlecloudsdk.core import log

DISK_METAVAR = (
    'name=NAME [mode={ro,rw}] [boot={yes,no}] [device-name=DEVICE_NAME] '
    '[auto-delete={yes,no}]')

DETAILED_HELP = {
    'brief': 'Create Compute Engine virtual machine instances',
    'DESCRIPTION': """\
        *{command}* facilitates the creation of Google Compute Engine
        virtual machines. For example, running:

          $ {command} example-instance-1 example-instance-2 example-instance-3 --zone us-central1-a

        will create three instances called 'example-instance-1',
        'example-instance-2', and 'example-instance-3' in the
        ``us-central1-a'' zone.

        For more examples, refer to the *EXAMPLES* section below.
        """,
    'EXAMPLES': """\
        To create an instance with the latest ``Red Hat Enterprise Linux
        6'' image available, run:

          $ {command} example-instance --image rhel-6 --zone us-central1-a
        """,
}


def _CommonArgs(parser):
  """Register parser args common to all tracks."""
  metadata_utils.AddMetadataArgs(parser)
  instance_utils.AddDiskArgs(parser)
  instance_utils.AddLocalSsdArgs(parser)
  instance_utils.AddImageArgs(parser)
  instance_utils.AddCanIpForwardArgs(parser)
  instance_utils.AddAddressArgs(parser, instances=True)
  instance_utils.AddMachineTypeArgs(parser)
  instance_utils.AddMaintenancePolicyArgs(parser)
  instance_utils.AddNetworkArgs(parser)
  instance_utils.AddNoRestartOnFailureArgs(parser)
  instance_utils.AddPreemptibleVmArgs(parser)
  instance_utils.AddScopeArgs(parser)
  instance_utils.AddTagsArgs(parser)

  parser.add_argument(
      '--description',
      help='Specifies a textual description of the instances.')

  parser.add_argument(
      'names',
      metavar='NAME',
      nargs='+',
      help='The names of the instances to create.')

  utils.AddZoneFlag(
      parser,
      resource_type='instances',
      operation_type='create')


def _ValidateDiskFlags(args):
  """Validates the values of all disk-related flags."""

  boot_disk_specified = False

  for disk in args.disk or []:
    disk_name = disk.get('name')
    if not disk_name:
      raise exceptions.ToolException(
          '[name] is missing in [--disk]. [--disk] value must be of the form '
          '[{0}].'.format(DISK_METAVAR))

    mode_value = disk.get('mode')
    if mode_value and mode_value not in ('rw', 'ro'):
      raise exceptions.ToolException(
          'Value for [mode] in [--disk] must be [rw] or [ro], not [{0}].'
          .format(mode_value))

    # Ensures that the user is not trying to attach a read-write
    # disk to more than one instance.
    if len(args.names) > 1 and mode_value == 'rw':
      raise exceptions.ToolException(
          'Cannot attach disk [{0}] in read-write mode to more than one '
          'instance.'.format(disk_name))

    boot_value = disk.get('boot')
    if boot_value and boot_value not in ('yes', 'no'):
      raise exceptions.ToolException(
          'Value for [boot] in [--disk] must be [yes] or [no], not [{0}].'
          .format(boot_value))

    auto_delete_value = disk.get('auto-delete')
    if auto_delete_value and auto_delete_value not in ['yes', 'no']:
      raise exceptions.ToolException(
          'Value for [auto-delete] in [--disk] must be [yes] or [no], not '
          '[{0}].'.format(auto_delete_value))

    # If this is a boot disk and we have already seen a boot disk,
    # we need to fail because only one boot disk can be attached.
    if boot_value == 'yes':
      if boot_disk_specified:
        raise exceptions.ToolException(
            'Each instance can have exactly one boot disk. At least two '
            'boot disks were specified through [--disk].')
      else:
        boot_disk_specified = True

  if args.image and boot_disk_specified:
    raise exceptions.ToolException(
        'Each instance can have exactly one boot disk. One boot disk '
        'was specified through [--disk] and another through [--image].')

  if boot_disk_specified:
    if args.boot_disk_device_name:
      raise exceptions.ToolException(
          '[--boot-disk-device-name] can only be used when creating a new '
          'boot disk.')

    if args.boot_disk_type:
      raise exceptions.ToolException(
          '[--boot-disk-type] can only be used when creating a new boot '
          'disk.')

    if args.boot_disk_size:
      raise exceptions.ToolException(
          '[--boot-disk-size] can only be used when creating a new boot '
          'disk.')

    if args.no_boot_disk_auto_delete:
      raise exceptions.ToolException(
          '[--no-boot-disk-auto-delete] can only be used when creating a '
          'new boot disk.')


def _UseExistingBootDisk(args):
  """Returns True if the user has specified an existing boot disk."""
  return any(disk.get('boot') == 'yes' for disk in args.disk or [])


@base.ReleaseTracks(base.ReleaseTrack.GA)
class CreateGA(base_classes.BaseAsyncCreator,
               image_utils.ImageExpander,
               addresses_utils.AddressExpander,
               zone_utils.ZoneResourceFetcher):
  """Create Google Compute Engine virtual machine instances."""

  @staticmethod
  def Args(parser):
    _CommonArgs(parser)

  @property
  def service(self):
    return self.compute.instances

  @property
  def method(self):
    return 'Insert'

  @property
  def resource_type(self):
    return 'instances'

  def CreatePersistentAttachedDiskMessages(self, args, instance_ref):
    """Returns a list of AttachedDisk messages and the boot disk's reference."""
    disks = []
    boot_disk_ref = None

    for disk in args.disk or []:
      name = disk['name']

      # Resolves the mode.
      mode_value = disk.get('mode', 'rw')
      if mode_value == 'rw':
        mode = self.messages.AttachedDisk.ModeValueValuesEnum.READ_WRITE
      else:
        mode = self.messages.AttachedDisk.ModeValueValuesEnum.READ_ONLY

      boot = disk.get('boot') == 'yes'
      auto_delete = disk.get('auto-delete') == 'yes'

      disk_ref = self.CreateZonalReference(
          name, instance_ref.zone,
          resource_type='disks')
      if boot:
        boot_disk_ref = disk_ref

      if self.csek_keys:
        disk_key_or_none = self.csek_keys.LookupKey(disk_ref)
        kwargs = {'diskEncryptionKey': disk_key_or_none}
      else:
        kwargs = {}

      attached_disk = self.messages.AttachedDisk(
          autoDelete=auto_delete,
          boot=boot,
          deviceName=disk.get('device-name'),
          mode=mode,
          source=disk_ref.SelfLink(),
          type=self.messages.AttachedDisk.TypeValueValuesEnum.PERSISTENT,
          **kwargs)

      # The boot disk must end up at index 0.
      if boot:
        disks = [attached_disk] + disks
      else:
        disks.append(attached_disk)

    return disks, boot_disk_ref

  def CreateDefaultBootAttachedDiskMessage(
      self, args, boot_disk_size_gb, image_uri, instance_ref):
    """Returns an AttachedDisk message for creating a new boot disk."""

    if args.boot_disk_type:
      disk_type_ref = self.CreateZonalReference(
          args.boot_disk_type, instance_ref.zone,
          resource_type='diskTypes')
      disk_type_uri = disk_type_ref.SelfLink()
    else:
      disk_type_ref = None
      disk_type_uri = None

    if self.csek_keys:
      # If we're going to encrypt the boot disk make sure that we select
      # a name predictably, instead of letting the API deal with name
      # conflicts automatically.
      #
      # Note that when csek keys are being used we *always* want force this
      # even if we don't have any encryption key for default disk name.
      #
      # Consider the case where the user's key file has a key for disk `foo-1`
      # and no other disk.  Assume she runs
      #   gcloud compute instances create foo --csek-key-file f \
      #       --no-requires-csek-key-create
      # and gcloud doesn't force the disk name to be `foo`.  The API might
      # select name `foo-1` for the new disk, but has no way of knowing
      # that the user has a key file mapping for that disk name.  That
      # behavior violates the principle of least surprise.
      #
      # Instead it's better for gcloud to force a specific disk name in the
      # instance create, and fail if that name isn't available.

      effective_boot_disk_name = (
          args.boot_disk_device_name or instance_ref.Name())

      disk_ref = self.CreateZonalReference(
          effective_boot_disk_name, instance_ref.zone,
          resource_type='disks')
      disk_key_or_none = self.csek_keys.LookupKey(
          disk_ref, not args.no_require_csek_key_create)
      [image_key_or_none] = csek_utils.MaybeLookupKeysByUri(
          self.csek_keys, self.resources, [image_uri])
      kwargs_init_parms = {'sourceImageEncryptionKey': image_key_or_none}
      kwargs_disk = {'diskEncryptionKey': disk_key_or_none}
    else:
      kwargs_disk = {}
      kwargs_init_parms = {}
      effective_boot_disk_name = args.boot_disk_device_name

    return self.messages.AttachedDisk(
        autoDelete=not args.no_boot_disk_auto_delete,
        boot=True,
        deviceName=effective_boot_disk_name,
        initializeParams=self.messages.AttachedDiskInitializeParams(
            sourceImage=image_uri,
            diskSizeGb=boot_disk_size_gb,
            diskType=disk_type_uri,
            **kwargs_init_parms),
        mode=self.messages.AttachedDisk.ModeValueValuesEnum.READ_WRITE,
        type=self.messages.AttachedDisk.TypeValueValuesEnum.PERSISTENT,
        **kwargs_disk)

  def FetchDiskResources(self, disk_refs):
    """Returns a list of disk resources corresponding to the disk references."""
    requests = []
    for disk_ref in disk_refs:
      requests.append((
          self.compute.disks,
          'Get',
          self.messages.ComputeDisksGetRequest(
              disk=disk_ref.Name(),
              project=disk_ref.project,
              zone=disk_ref.zone)))
    errors = []
    res = list(request_helper.MakeRequests(
        requests=requests,
        http=self.http,
        batch_url=self.batch_url,
        errors=errors,
        custom_get_requests=None))
    if errors:
      utils.RaiseToolException(
          errors,
          error_message='Could not fetch some boot disks:')
    return res

  def CreateServiceAccountMessages(self, args):
    """Returns a list of ServiceAccount messages corresponding to --scopes."""
    if args.no_scopes:
      scopes = []
    else:
      scopes = args.scopes or constants.DEFAULT_SCOPES

    accounts_to_scopes = collections.defaultdict(list)
    for scope in scopes:
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

      # Expands the scope if the user provided an alias like
      # "compute-rw".
      scope_uri = constants.SCOPES.get(scope_uri, scope_uri)

      accounts_to_scopes[account].append(scope_uri)

    res = []
    for account, scopes in sorted(accounts_to_scopes.iteritems()):
      res.append(self.messages.ServiceAccount(
          email=account,
          scopes=sorted(scopes)))
    return res

  def CreateNetworkInterfaceMessage(self, args, instance_refs):
    """Returns a new NetworkInterface message."""
    network_ref = self.CreateGlobalReference(
        args.network, resource_type='networks')
    network_interface = self.messages.NetworkInterface(
        network=network_ref.SelfLink())

    if not args.no_address:
      access_config = self.messages.AccessConfig(
          name=constants.DEFAULT_ACCESS_CONFIG_NAME,
          type=self.messages.AccessConfig.TypeValueValuesEnum.ONE_TO_ONE_NAT)

      # If the user provided an external IP, populate the access
      # config with it.
      if len(instance_refs) == 1:
        region = utils.ZoneNameToRegionName(instance_refs[0].zone)
        address = self.ExpandAddressFlag(args, region)
        if address:
          access_config.natIP = address

      network_interface.accessConfigs = [access_config]

    return network_interface

  def CreateRequests(self, args):
    _ValidateDiskFlags(args)
    instance_utils.ValidateLocalSsdFlags(args)

    # TODO(user) drop test after CSEK goes GA
    if hasattr(args, 'csek_key_file'):
      self.csek_keys = csek_utils.CsekKeyStore.FromArgs(args)
    else:
      self.csek_keys = None

    if args.maintenance_policy:
      on_host_maintenance = (
          self.messages.Scheduling.OnHostMaintenanceValueValuesEnum(
              args.maintenance_policy))
    else:
      on_host_maintenance = None

    # Note: We always specify automaticRestart=False for preemptible VMs. This
    # makes sense, since no-restart-on-failure is defined as "store-true", and
    # thus can't be given an explicit value. Hence it either has its default
    # value (in which case we override it for convenience's sake to the only
    # setting that makes sense for preemptible VMs), or the user actually
    # specified no-restart-on-failure, the only usable setting.
    if args.preemptible:
      scheduling = self.messages.Scheduling(
          automaticRestart=False,
          onHostMaintenance=on_host_maintenance,
          preemptible=True)
    else:
      scheduling = self.messages.Scheduling(
          automaticRestart=not args.no_restart_on_failure,
          onHostMaintenance=on_host_maintenance)

    service_accounts = self.CreateServiceAccountMessages(args)

    if args.tags:
      tags = self.messages.Tags(items=args.tags)
    else:
      tags = None

    metadata = metadata_utils.ConstructMetadataMessage(
        self.messages,
        metadata=args.metadata,
        metadata_from_file=args.metadata_from_file)

    # If the user already provided an initial Windows password and
    # username through metadata, then there is no need to check
    # whether the image or the boot disk is Windows.
    windows_username_present = False
    windows_password_present = False
    for kv in metadata.items:
      if kv.key == constants.INITIAL_WINDOWS_USER_METADATA_KEY_NAME:
        windows_username_present = True
      if kv.key == constants.INITIAL_WINDOWS_PASSWORD_METADATA_KEY_NAME:
        windows_password_present = True
    check_for_windows_image = (not windows_username_present or
                               not windows_password_present)

    boot_disk_size_gb = utils.BytesToGb(args.boot_disk_size)
    utils.WarnIfDiskSizeIsTooSmall(boot_disk_size_gb, args.boot_disk_type)

    instance_refs = self.CreateZonalReferences(args.names, args.zone)

    # Check if the zone is deprecated or has maintenance coming.
    self.WarnForZonalCreation(instance_refs)

    network_interface = self.CreateNetworkInterfaceMessage(args, instance_refs)

    # The element at index i is the machine type URI for instance
    # i. We build this list here because we want to delay work that
    # requires API calls as much as possible. This leads to a better
    # user experience because the tool can fail fast upon a spelling
    # mistake instead of delaying the user by making API calls whose
    # purpose has already been rendered moot by the spelling mistake.
    machine_type_uris = []
    for instance_ref in instance_refs:
      machine_type_uris.append(self.CreateZonalReference(
          args.machine_type, instance_ref.zone,
          resource_type='machineTypes').SelfLink())

    create_boot_disk = not _UseExistingBootDisk(args)
    add_windows_credentials_to_metadata = False
    if create_boot_disk:
      image_uri, image_resource = self.ExpandImageFlag(
          args, return_image_resource=check_for_windows_image)
      if (check_for_windows_image and
          image_utils.HasWindowsLicense(image_resource, self.resources)):
        log.debug('[%s] is a Windows image.', image_resource.selfLink)
        add_windows_credentials_to_metadata = True

      # TODO(user): Rip this section out along with the other windows
      # passwod stuff on ~20150506 (also remove 'import re' at the top)
      # We should only match on images that are named exactly the way the
      # images team names the images.
      p = re.compile(r'windows-server-20\d\d(-r2)*-(dc|ent-internal)'
                     r'-v(\d\d\d\d\d\d\d\d)')
      if image_resource and p.match(image_resource.name):
        datestamp = int(p.match(image_resource.name).group(3))
        # Don't set Windows credentials for any Windows image built after 4/20.
        if datestamp > 20150420:
          add_windows_credentials_to_metadata = False
    else:
      image_uri = None

    # A list of lists where the element at index i contains a list of
    # disk messages that should be set for the instance at index i.
    disks_messages = []

    # A mapping of zone to boot disk references for all existing boot
    # disks that are being attached.
    # TODO(user): Simplify this once resources.Resource becomes
    # hashable.
    existing_boot_disks = {}

    for instance_ref in instance_refs:
      persistent_disks, boot_disk_ref = (
          self.CreatePersistentAttachedDiskMessages(args, instance_ref))
      local_ssds = [
          instance_utils.CreateLocalSsdMessage(
              self, x.get('device-name'), x.get('interface'), instance_ref.zone)
          for x in args.local_ssd or []]
      if create_boot_disk:
        boot_disk = self.CreateDefaultBootAttachedDiskMessage(
            args, boot_disk_size_gb, image_uri, instance_ref)
        persistent_disks = [boot_disk] + persistent_disks
      else:
        existing_boot_disks[boot_disk_ref.zone] = boot_disk_ref
      disks_messages.append(persistent_disks + local_ssds)

    # Now for every existing boot disk being attached, we have to
    # figure out whether it has a Windows license.
    if check_for_windows_image and existing_boot_disks:
      # Sorts the disk references by zone, so the code behaves
      # deterministically.
      disk_resources = self.FetchDiskResources(
          disk_ref for _, disk_ref in sorted(existing_boot_disks.iteritems()))
      for disk_resource in disk_resources:
        if image_utils.HasWindowsLicense(disk_resource, self.resources):
          log.debug('[%s] has a Windows image.', disk_resource.selfLink)
          add_windows_credentials_to_metadata = True

    # When the user creates more than one instance, it's possible for
    # some instances to have boot disks that have been initialized
    # with Windows images while others have boot disks without Windows
    # images:
    #
    #     gcloud compute instances create
    #       https://.../zone-1/instances/i-1
    #       https://.../zone-2/instances/i-
    #       --disk name=x boot=yes
    #
    # In the above, disk "x" in zone-1 could be a Windows disk while
    # "x" in zone-2 could be a non-Windows disk. When this case is
    # encountered, we add the Windows username and password to all
    # instances because to write code to deal with such a rare case is
    # simply not worth the added complexity.
    if add_windows_credentials_to_metadata:
      if not windows_username_present:
        username = self.project.split(':')[-1][
            :constants.MAX_WINDOWS_USERNAME_LENGTH]
        metadata.items.append(self.messages.Metadata.ItemsValueListEntry(
            key=constants.INITIAL_WINDOWS_USER_METADATA_KEY_NAME,
            value=username))

      if not windows_password_present:
        metadata.items.append(self.messages.Metadata.ItemsValueListEntry(
            key=constants.INITIAL_WINDOWS_PASSWORD_METADATA_KEY_NAME,
            value=windows_password.Generate()))

    requests = []
    for instance_ref, machine_type_uri, disks in zip(
        instance_refs, machine_type_uris, disks_messages):
      requests.append(self.messages.ComputeInstancesInsertRequest(
          instance=self.messages.Instance(
              canIpForward=args.can_ip_forward,
              disks=disks,
              description=args.description,
              machineType=machine_type_uri,
              metadata=metadata,
              name=instance_ref.Name(),
              networkInterfaces=[network_interface],
              serviceAccounts=service_accounts,
              scheduling=scheduling,
              tags=tags,
          ),
          project=self.project,
          zone=instance_ref.zone))

    return requests


@base.ReleaseTracks(base.ReleaseTrack.BETA)
class CreateBeta(CreateGA):

  @staticmethod
  def Args(parser):
    _CommonArgs(parser)


@base.ReleaseTracks(base.ReleaseTrack.ALPHA)
class CreateAlpha(CreateBeta):

  @staticmethod
  def Args(parser):
    _CommonArgs(parser)
    csek_utils.AddCsekKeyArgs(parser)

CreateAlpha.detailed_help = DETAILED_HELP
CreateBeta.detailed_help = DETAILED_HELP
CreateGA.detailed_help = DETAILED_HELP
