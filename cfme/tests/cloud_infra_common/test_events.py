# -*- coding: utf-8 -*-
"""This module tests events that are invoked by Cloud/Infra VMs."""
import fauxfactory
import pytest

from cfme.common.provider import BaseProvider
from cfme.common.vm import VM
from cfme.control.explorer.policies import VMControlPolicy
from cfme.infrastructure.provider.rhevm import RHEVMProvider
from cfme.utils.blockers import BZ
from cfme.utils.wait import wait_for


pytestmark = [
    pytest.mark.usefixtures('uses_infra_providers', 'uses_cloud_providers'),
    pytest.mark.tier(2),
    pytest.mark.provider([BaseProvider],
                         required_fields=['provisioning'],
                         scope='module'),
]


@pytest.yield_fixture(scope="function")
def vm_crud(provider, setup_provider_modscope, small_template_modscope):
    template = small_template_modscope
    vm = VM.factory(
        'test_events_{}'.format(fauxfactory.gen_alpha(length=8).lower()),
        provider,
        template_name=template.name)
    yield vm
    if vm.does_vm_exist_on_provider():
        vm.cleanup_on_provider()


@pytest.mark.rhv2
@pytest.mark.uncollectif(lambda provider: provider.one_of(RHEVMProvider) and
                         BZ(1509020, forced_streams=['5.8', '5.9']).blocks,
                         'BZ 1509020')
def test_vm_create(request, appliance, vm_crud, provider, register_event):
    """ Test whether vm_create_complete event is emitted.

    Prerequisities:
        * A provider that is set up and able to deploy VMs

    Steps:
        * Create a Control setup (action, policy, profile) that apply a tag on a VM when
            ``VM Create Complete`` event comes
        * Deploy the VM outside of CFME (directly in the provider)
        * Refresh provider relationships and wait for VM to appear
        * Assert the tag appears.

    Metadata:
        test_flag: provision
    """
    action = appliance.collections.actions.create(
        fauxfactory.gen_alpha(),
        "Tag",
        dict(tag=("My Company Tags", "Environment", "Development")))
    request.addfinalizer(action.delete)

    policy = appliance.collections.policies.create(
        VMControlPolicy,
        fauxfactory.gen_alpha()
    )
    request.addfinalizer(policy.delete)

    policy.assign_events("VM Create Complete")
    request.addfinalizer(policy.assign_events)
    policy.assign_actions_to_event("VM Create Complete", action)

    profile = appliance.collections.policy_profiles.create(
        fauxfactory.gen_alpha(), policies=[policy])
    request.addfinalizer(profile.delete)

    provider.assign_policy_profiles(profile.description)
    request.addfinalizer(lambda: provider.unassign_policy_profiles(profile.description))

    register_event(target_type='VmOrTemplate', target_name=vm_crud.name, event_type='vm_create')

    vm_crud.create_on_provider(find_in_cfme=True)

    def _check():
        return any(tag.category.display_name == "Environment" and tag.display_name == "Development"
                   for tag in vm_crud.get_tags())

    wait_for(_check, num_sec=300, delay=15, message="tags to appear")
