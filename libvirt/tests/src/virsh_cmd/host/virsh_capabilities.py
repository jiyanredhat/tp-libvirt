import logging

from autotest.client import os_dep
from autotest.client.shared import error

from avocado.utils import process

from virttest import libvirt_vm
from virttest import virsh
from virttest import utils_libvirtd
from virttest.libvirt_xml import capability_xml


def run(test, params, env):
    """
    Test the command virsh capabilities

    (1) Call virsh capabilities
    (2) Call virsh capabilities with an unexpected option
    (3) Call virsh capabilities with libvirtd service stop
    """
    def compare_capabilities_xml(source):
        cap_xml = capability_xml.CapabilityXML()
        cap_xml.xml = source

        # Check that host has a non-empty UUID tag.
        xml_uuid = cap_xml.uuid
        logging.debug("Host UUID (capabilities_xml): %s", xml_uuid)
        if xml_uuid == "":
            raise error.TestFail("The host uuid in capabilities_xml is none!")

        # Check the host arch.
        xml_arch = cap_xml.arch
        logging.debug("Host arch (capabilities_xml): %s", xml_arch)
        exp_arch = process.run("arch", shell=True).stdout.strip()
        if cmp(xml_arch, exp_arch) != 0:
            raise error.TestFail("The host arch in capabilities_xml is "
                                 "expected to be %s, but get %s" %
                                 (exp_arch, xml_arch))

        # Check the host cpu count.
        xml_cpu_count = cap_xml.cpu_count
        logging.debug("Host cpus count (capabilities_xml): %s", xml_cpu_count)
        cmd = "grep processor /proc/cpuinfo | wc -l"
        exp_cpu_count = int(process.run(cmd, shell=True).stdout.strip())
        if xml_cpu_count != exp_cpu_count:
            raise error.TestFail("Host cpus count is expected to be %s, "
                                 "but get %s" %
                                 (exp_cpu_count, xml_cpu_count))

        # Check the arch of guest supported.
        guest_capa = cap_xml.get_guest_capabilities()
        logging.debug(guest_capa)

        # libvirt track wordsize in hardcode struct virArchData
        wordsize = {}
        wordsize['64'] = ['alpha', 'aarch64', 'ia64', 'mips64', 'mips64el',
                          'parisc64', 'ppc64', 'ppc64le', 's390x', 'sh4eb',
                          'sparc64', 'x86_64']
        wordsize['32'] = ['armv6l', 'armv7l', 'armv7b', 'cris', 'i686', 'lm32',
                          'm68k', 'microblaze', 'microblazeel', 'mips',
                          'mipsel', 'openrisc', 'parisc', 'ppc', 'ppcle',
                          'ppcemb', 's390', 'sh4', 'sparc', 'unicore32',
                          'xtensa', 'xtensaeb']
        uri_type = process.run("virsh uri", shell=True).stdout.split(':')[0]
        domain_type = "domain_" + uri_type
        for arch_dict in guest_capa.values():
            for arch, val_dict in arch_dict.items():
                # Check wordsize
                if arch not in wordsize[val_dict['wordsize']]:
                    raise error.TestFail("'%s' wordsize '%s' in "
                                         "capabilities_xml not expected" %
                                         (arch, val_dict['wordsize']))
                # Check the type of hypervisor
                if domain_type not in val_dict.keys():
                    raise error.TestFail("domain type '%s' is not matched"
                                         " under arch '%s' in "
                                         "capabilities_xml" %
                                         (uri_type, arch))

        # check power management support.
        try:
            pm_cmd = os_dep.command('pm-is-supported')
            pm_cap_map = {'suspend': 'suspend_mem',
                          'hibernate': 'suspend_disk',
                          'suspend-hybrid': 'suspend_hybrid'}
            exp_pms = []
            for opt in pm_cap_map:
                cmd = '%s --%s' % (pm_cmd, opt)
                res = process.run(cmd, ignore_status=True, shell=True)
                if res.exit_status == 0:
                    exp_pms.append(pm_cap_map[opt])
            pms = cap_xml.power_management_list
            if set(exp_pms) != set(pms):
                raise error.TestFail("Expected supported PMs are %s, got %s "
                                     "instead." % (exp_pms, pms))
        except ValueError:
            logging.debug('Power management checking is skipped, since command'
                          ' pm-is-supported is not found.')

    connect_uri = libvirt_vm.normalize_connect_uri(params.get("connect_uri",
                                                              "default"))

    # Prepare libvirtd service
    if "libvirtd" in params:
        libvirtd = params.get("libvirtd")
        if libvirtd == "off":
            utils_libvirtd.libvirtd_stop()

    # Run test case
    option = params.get("virsh_cap_options")
    try:
        output = virsh.capabilities(option, uri=connect_uri,
                                    ignore_status=False, debug=True)
        status = 0  # good
    except process.CmdError:
        status = 1  # bad
        output = ''

    # Recover libvirtd service start
    if libvirtd == "off":
        utils_libvirtd.libvirtd_start()

    # Check status_error
    status_error = params.get("status_error")
    if status_error == "yes":
        if status == 0:
            if libvirtd == "off":
                raise error.TestFail("Command 'virsh capabilities' succeeded "
                                     "with libvirtd service stopped, "
                                     "incorrect")
            else:
                raise error.TestFail("Command 'virsh capabilities %s' "
                                     "succeeded (incorrect command)" % option)
    elif status_error == "no":
        compare_capabilities_xml(output)
        if status != 0:
            raise error.TestFail("Command 'virsh capabilities %s' failed "
                                 "(correct command)" % option)
