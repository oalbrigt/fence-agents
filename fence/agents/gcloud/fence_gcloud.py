#!@PYTHON@ -tt

import sys, re
import logging
import atexit
sys.path.append("/usr/share/fence")
from fencing import *
from fencing import fail, fail_usage, EC_TIMED_OUT, run_delay

def get_nodes_list(compute, options):
	result = {}
	if compute:
		instances =  compute.instances().list(project=project, zone=zone).execute()['items']
		for instance in instances:
				result[instance["name"]] = ("", None)

	return result

def get_power_status(compute, options):
	if compute:
		instances =  compute.instances().list(project=project, zone=zone).execute()['items']
		for instance in instances:
			if instance["name"] == options["--plug"]:
				### TODO ??? running ??? ###
				if instance["status"] == "running":
						return "on"

	return "off"

def set_power_status(compute, options):
	if compute:
		if (options["--action"]=="off"):
			request = compute.instances().stop(project=project, zone=zone, instance=options["--plug"])
			request.execute()
		elif (options["--action"]=="on"):
			request = compute.instances().start(project=project, zone=zone, instance=options["--plug"])
			request.execute()


def define_new_opts():
	### TODO ###
	all_opt["project"] = {
		"getopt" : "p:",
		"longopt" : "project",
		"help" : "-p, --project=[name]           Project",
		"shortdesc" : "Project.",
		"required" : "0",
		"order" : 2
	}
	all_opt["zone"] = {
		"getopt" : "z:",
		"longopt" : "zone",
		"help" : "-z, --zone=[name]              Zone",
		"shortdesc" : "Zone.",
		"required" : "0",
		"order" : 3
	}

# Main agent method
def main():
	compute = None

	### TODO ###
	device_opt = ["port", "no_password", "project", "zone"]

	atexit.register(atexit_handler)

	define_new_opts()
	options = check_input(device_opt, process_input(device_opt))

	docs = {}
	### TODO ###
	docs["shortdesc"] = "Fence agent for Google Cloud"
	docs["longdesc"] = "fence_gcloud is an I/O Fencing agent for Google Cloud.\
It uses the Google API Client Python library to connect to Google Cloud.\
\n.P\n\
Authentication is done with \"glcoud init\" from the Google Cloud SDK.\n\
For instructions see: https://cloud.google.com/sdk/docs/#linux"
	docs["vendorurl"] = "http://www.google.com"
	show_docs(options, docs)

	run_delay(options)

	try:
		from oauth2client.client import GoogleCredentials
		from googleapiclient import discovery
	except ImportError:
		### TODO ###
		fail_usage("Google API Client Python library not available")

	credentials = GoogleCredentials.get_application_default()
	compute = discovery.build('compute', 'v1', credentials=credentials)

	# Operate the fencing device
	result = fence_action(compute, options, set_power_status, get_power_status, get_nodes_list)
	sys.exit(result)

if __name__ == "__main__":
	main()
