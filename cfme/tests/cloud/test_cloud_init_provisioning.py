# -*- coding: utf-8 -*-
# These tests don't work at the moment, due to the security_groups multi select not working
# in selenium (the group is selected then immediately reset)
import fauxfactory
import pytest
from widgetastic.utils import partial_match

from cfme.cloud.provider import CloudProvider
from cfme.cloud.provider.openstack import OpenStackProvider
from cfme.infrastructure.pxe import get_template_from_config
from cfme.utils import ssh
from cfme.utils.log import logger
from cfme.utils.wait import wait_for

pytestmark = [
    pytest.mark.meta(server_roles="+automate"),
    pytest.mark.provider([CloudProvider], required_fields=[
        ['provisioning', 'ci-template'],
        ['provisioning', 'ci-username'],
        ['provisioning', 'ci-pass'],
        ['provisioning', 'image']],
        scope="module")
]


@pytest.fixture(scope="module")
def setup_ci_template(provider, appliance):
    cloud_init_template_name = provider.data['provisioning']['ci-template']
    get_template_from_config(
        cloud_init_template_name,
        create=True, appliance=appliance)


@pytest.fixture(scope="function")
def vm_name(request):
    vm_name = 'test_image_prov_{}'.format(fauxfactory.gen_alphanumeric())
    return vm_name


@pytest.mark.tier(3)
def test_provision_cloud_init(appliance, request, setup_provider, provider, provisioning,
                              setup_ci_template, vm_name):
    """ Tests provisioning from a template with cloud_init

    Metadata:
        test_flag: cloud_init, provision
    """
    image = provisioning.get('ci-image') or provisioning['image']['name']
    note = ('Testing provisioning from image {} to vm {} on provider {}'.format(
        image, vm_name, provider.key))
    logger.info(note)

    mgmt_system = provider.mgmt

    # TODO: extend inst_args for other providers except EC2 if needed
    inst_args = {
        'request': {'email': 'image_provisioner@example.com',
                    'first_name': 'Image',
                    'last_name': 'Provisioner',
                    'notes': note},
        'catalog': {'vm_name': vm_name},
        'properties': {'instance_type': partial_match(provisioning['instance_type']),
                       'guest_keypair': provisioning['guest_keypair']},
        'environment': {'availability_zone': provisioning['availability_zone'],
                        'cloud_network': provisioning['cloud_network'],
                        'security_groups': [provisioning['security_group']]},
        'customize': {'custom_template': {'name': provisioning['ci-template']}}
    }

    # for image selection in before_fill
    inst_args['template_name'] = image

    if provider.one_of(OpenStackProvider):
        floating_ip = mgmt_system.get_first_floating_ip()
        inst_args['environment']['public_ip_address'] = floating_ip

    logger.info('Instance args: {}'.format(inst_args))

    instance = appliance.collections.cloud_instances.create(vm_name, provider, inst_args)
    request.addfinalizer(instance.delete_from_provider)
    provision_request = provider.appliance.collections.requests.instantiate(vm_name,
                                                                   partial_check=True)
    provision_request.wait_for_request()
    connect_ip = mgmt_system.get_ip_address(vm_name)

    # Check that we can at least get the uptime via ssh this should only be possible
    # if the username and password have been set via the cloud-init script so
    # is a valid check
    with ssh.SSHClient(hostname=connect_ip, username=provisioning['ci-username'],
                       password=provisioning['ci-pass']) as ssh_client:
        wait_for(ssh_client.uptime, num_sec=200, handle_exception=True)
