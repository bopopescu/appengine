# Copyright 2014 Google Inc. All Rights Reserved.

"""Default value constants exposed by core utilities."""

DEFAULT_REGISTRY = 'gcr.io'
REGIONAL_REGISTRIES = ['us.gcr.io', 'eu.gcr.io', 'asia.gcr.io']
ALL_SUPPORTED_REGISTRIES = [DEFAULT_REGISTRY] + REGIONAL_REGISTRIES
DEFAULT_DEVSHELL_IMAGE = (DEFAULT_REGISTRY +
                          '/dev_con/cloud-dev-common:prod')

# TODO(user): Change to container_prod
METADATA_IMAGE = DEFAULT_REGISTRY + '/_b_containers_qa/faux-metadata:latest'
