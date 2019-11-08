#!@PYTHON@ -tt

import sys, re, pexpect
import logging
import atexit
import xml.etree.ElementTree as ET
sys.path.append("@FENCEAGENTSLIBDIR@")
from fencing import *
from fencing import fail_usage, fail, EC_TIMED_OUT
from fencing import run_command, run_delay
import azure_fence

from requests.exceptions import ConnectionError
logging.getLogger("adal-python").setLevel(logging.CRITICAL)


def get_nodes_list(clients, options):
    result = {}

    if clients:
        instance_client = clients[0]
        rgName = options["--resourceGroup"]

        try:
            if options["--type"] == "vm":
                instances = instance_client.virtual_machines.list(rgName, proxies={"https": options["--proxy"]})
            elif options["--type"] == "hana":
                instances = instance_client.hana_instances.list_by_resource_group(rgName, proxies={"https": options["--proxy"]})
        except ConnectionError:
            fail(EC_TIMED_OUT)
        except Exception as e:
            fail_usage("Failed: %s" % e)

        for instance in instances:
            result[instance.name] = ("", None)

    return result

def check_unfence(clients, options):
    if clients:
        instance_client = clients[0]
        network_client = clients[1]
        rgName = options["--resourceGroup"]

        try:
            vms = instance_client.virtual_machines.list(rgName, proxies={"https": options["--proxy"]})
        except ConnectionError:
            fail(EC_TIMED_OUT)
        except Exception as e:
            fail_usage("Failed: %s" % e)

        for vm in vms:
            vmName = vm.name
            if azure_fence.get_network_state(instance_client, network_client, rgName, vmName) == "off":
                logging.info("Found fenced node " + vmName)
                # dont return "off" based on network-fencing status
                options.pop("--network-fencing", None)
                options["--plug"] = vmName
                if get_power_status(clients, options) == "off":
                    logging.info("Unfencing " + vmName)
                    options["--network-fencing"] = ""
                    options["--action"] = "on"
                    set_power_status(clients, options)
                    options["--action"] = "monitor"

def get_power_status(clients, options):
    state = { "running": "on",
                "started": "on",
                "deallocated": "off",
                "stopped": "off" }
    logging.info("getting power status for VM " + options["--plug"])

    if clients:
        instance_client = clients[0]
        rgName = options["--resourceGroup"]
        instanceName = options["--plug"]

        if "--network-fencing" in options:
            network_client = clients[1]
            netState =  azure_fence.get_network_state(instance_client, network_client, rgName, instanceName)
            logging.info("Found network state of VM: " + netState)

            # return off quickly once network is fenced instead of waiting for vm state to change
            if options["--action"] == "off" and netState == "off":
                logging.info("Network fenced for " + instanceName)
                return netState

        powerState = "unknown"
        try:
            if options["--type"] == "vm":
                instanceStatus = instance_client.virtual_machines.get(rgName, instanceName, "instanceView", proxies={"https": options["--proxy"]})
                for status in instanceStatus.instance_view.statuses:
                    if status.code.startswith("PowerState"):
                        powerState = status.code.split("/")[1]
                        break
            elif options["--type"] == "hana":
                instanceStatus = instance_client.hana_instances.get(rgName.encode(), instanceName.encode(), proxies={"https": options["--proxy"]})
                powerState = instanceStatus.power_state
        except ConnectionError:
            fail(EC_TIMED_OUT)
        except Exception as e:
            fail_usage("Failed: %s" % e)

        instanceState = state.get(powerState, "unknown")
        logging.info("Found power state of VM: %s (%s)" % (instanceState, powerState))

        if "--network-fencing" in options and netState == "off":
            return "off"

        if options["--action"] != "on" and instanceState != "off":
            return "on"

        if instanceState == "on":
            return "on"

        return "off"

def set_power_status(clients, options):
    logging.info("setting power status for VM " + options["--plug"] + " to " + options["--action"])

    if clients:
        instance_client = clients[0]
        rgName = options["--resourceGroup"]
        instanceName = options["--plug"]
        hana_headers={"Content-Type": "application/json; charset=utf-8"}

        try:
            if "--network-fencing" in options:
                network_client = clients[1]

                if (options["--action"]=="off"):
                    logging.info("Fencing network for " + instanceName)
                    azure_fence.set_network_state(instance_client, network_client, rgName, instanceName, "block")
                elif (options["--action"]=="on"):
                    logging.info("Unfencing network for " + instanceName)
                    azure_fence.set_network_state(instance_client, network_client, rgName, instanceName, "unblock")

            if (options["--action"]=="off"):
                logging.info("Poweroff " + instanceName + " in resource group " + rgName)
                if options["--type"] == "vm":
                    instance_client.virtual_machines.power_off(rgName, instanceName, skip_shutdown=True, proxies={"https": options["--proxy"]})
                elif options["--type"] == "hana":
                    instanceStatus = instance_client.hana_instances.shutdown(rgName, instanceName, skip_shutdown=True, custom_headers=hana_headers, proxies={"https": options["--proxy"]})
            elif (options["--action"]=="on"):
                logging.info("Starting " + instanceName + " in resource group " + rgName)
                if options["--type"] == "vm":
                    instance_client.virtual_machines.start(rgName, instanceName, proxies={"https": options["--proxy"]})
                elif options["--type"] == "hana":
                    instance_client.hana_instances.start(rgName, instanceName, custom_headers=hana_headers, proxies={"https": options["--proxy"]})
        except ConnectionError:
            fail(EC_TIMED_OUT)
        except:
            pass


def define_new_opts():
    all_opt["type"] = {
        "getopt" : ":",
        "longopt" : "type",
        "help" : "--type=[type]                  Type (e.g. vm or hana)",
        "shortdesc" : "Type of machine (e.g. vm or hana)",
        "default" : "vm",
        "required" : "0",
        "order" : 2
    }
    all_opt["resourceGroup"] = {
        "getopt" : ":",
        "longopt" : "resourceGroup",
        "help" : "--resourceGroup=[name]         Name of the resource group",
        "shortdesc" : "Name of resource group. Metadata service is used if the value is not provided.",
        "required" : "0",
        "order" : 3
    }
    all_opt["tenantId"] = {
        "getopt" : ":",
        "longopt" : "tenantId",
        "help" : "--tenantId=[name]              Id of the Azure Active Directory tenant",
        "shortdesc" : "Id of Azure Active Directory tenant.",
        "required" : "0",
        "order" : 4
    }
    all_opt["subscriptionId"] = {
        "getopt" : ":",
        "longopt" : "subscriptionId",
        "help" : "--subscriptionId=[name]        Id of the Azure subscription",
        "shortdesc" : "Id of the Azure subscription. Metadata service is used if the value is not provided.",
        "required" : "0",
        "order" : 5
    }
    all_opt["network-fencing"] = {
        "getopt" : "",
        "longopt" : "network-fencing",
        "help" : "--network-fencing              Use network fencing. See NOTE-section of\n\
                                  metadata for required Subnet/Network Security\n\
                                  Group configuration.",
        "shortdesc" : "Use network fencing. See NOTE-section for configuration.",
        "required" : "0",
        "order" : 6
    }
    all_opt["msi"] = {
        "getopt" : "",
        "longopt" : "msi",
        "help" : "--msi                          Use Managed Service Identity instead of\n\
                                  username and password. If specified,\n\
                                  parameters tenantId, login and passwd are not\n\
                                  allowed.",
        "shortdesc" : "Determines if Managed Service Identity should be used.",
        "required" : "0",
        "order" : 7
    }
    all_opt["cloud"] = {
        "getopt" : ":",
        "longopt" : "cloud",
        "help" : "--cloud=[name]                 Name of the cloud you want to use. Supported\n\
                                  values are china, germany or usgov. Do not use\n\
                                  this parameter if you want to use public\n\
                                  Azure.",
        "shortdesc" : "Name of the cloud you want to use.",
        "required" : "0",
        "order" : 8
    }
    all_opt["proxy"] = {
        "getopt" : ":",
        "longopt" : "proxy",
        "help" : "--proxy=[proxy]                Proxy (e.g. http://192.168.1.2:3128).",
        "shortdesc" : "Proxy (e.g. http://192.168.1.2:3128).",
        "default" : "",
        "required" : "0",
        "order" : 9
    }

# Main agent method
def main():
    instance_client = None
    network_client = None

    device_opt = ["login", "passwd", "port", "type", "resourceGroup", "tenantId", "subscriptionId", "network-fencing", "msi", "cloud", "proxy"]

    atexit.register(atexit_handler)

    define_new_opts()

    all_opt["power_timeout"]["default"] = "150"

    all_opt["login"]["help"] = "-l, --username=[appid]         Application ID"
    all_opt["passwd"]["help"] = "-p, --password=[authkey]       Authentication key"

    options = check_input(device_opt, process_input(device_opt))

    docs = {}
    docs["shortdesc"] = "Fence agent for Azure Resource Manager"
    docs["longdesc"] = "fence_azure_arm is an I/O Fencing agent for Azure Resource Manager. It uses Azure SDK for Python to connect to Azure.\
\n.P\n\
For instructions to setup credentials see: https://docs.microsoft.com/en-us/azure/azure-resource-manager/resource-group-create-service-principal-portal\
\n.P\n\
Username and password are application ID and authentication key from \"App registrations\".\
\n.P\n\
NOTE: NETWORK FENCING\n.br\n\
Network fencing requires an additional Subnet named \"fence-subnet\" for the Virtual Network using a Network Security Group with the following rules:\n.br\n\
+-----------+-----+-------------------------+------+------+-----+-----+--------+\n.br\n\
| DIRECTION | PRI | NAME                    | PORT | PROT | SRC | DST | ACTION |\n.br\n\
+-----------+-----+-------------------------+------+------+-----+-----+--------+\n.br\n\
| Inbound   | 100 | FENCE_DENY_ALL_INBOUND  | Any  | Any  | Any | Any | Deny   |\n.br\n\
| Outbound  | 100 | FENCE_DENY_ALL_OUTBOUND | Any  | Any  | Any | Any | Deny   |\n.br\n\
+-----------+-----+-------------------------+------+------+-----+-----+--------+\
\n.P\n\
When using network fencing the reboot-action will cause a quick-return once the network has been fenced (instead of waiting for the off-action to succeed). It will check the status during the monitor-action, and request power-on when the shutdown operation is complete."
    docs["vendorurl"] = "http://www.microsoft.com"
    show_docs(options, docs)

    run_delay(options)

    try:
        config = azure_fence.get_azure_config(options)
        instance_client = azure_fence.get_azure_instance_client(config)
        if "--network-fencing" in options:
            network_client = azure_fence.get_azure_network_client(config)
    except ConnectionError:
        fail(EC_TIMED_OUT)
    except ImportError:
        fail_usage("Azure Resource Manager Python SDK not found or not accessible")
    except Exception as e:
        fail_usage("Failed: %s" % re.sub("^, ", "", str(e)))

    if "--network-fencing" in options:
        # use  off-action to quickly return off once network is fenced instead of
        # waiting for vm state to change
        if options["--action"] == "reboot":
            options["--action"] = "off"
        # check for devices to unfence in monitor-action
        elif options["--action"] == "monitor":
            check_unfence([instance_client, network_client], options)

    # Operate the fencing device
    result = fence_action([instance_client, network_client], options, set_power_status, get_power_status, get_nodes_list)
    sys.exit(result)

if __name__ == "__main__":
    main()
