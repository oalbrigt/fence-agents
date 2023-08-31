#!@PYTHON@ -tt

import sys
import pycurl, io, json
import logging
import atexit
sys.path.append("@FENCEAGENTSLIBDIR@")
from fencing import *
from fencing import fail, run_delay, EC_LOGIN_DENIED, EC_STATUS

if sys.version_info[0] > 2: import urllib.parse as urllib
else: import urllib

state = {"on": "on", "off": "off", "suspended": "off"}

def get_power_status(conn, options):
	try:
		res = send_command(conn, "vms/{}".format(options["--plug"]))["power_state"]
	except Exception as e:
		logging.debug("Failed: {}".format(e))
		fail(EC_STATUS)

	if len(res) == 0:
		fail(EC_STATUS)

	return state[res]

def set_power_status(conn, options):
	action = {
		"on" : '{"transition": "ON"}',
		"off" : '{"transition": "OFF"}'
	}[options["--action"]]

	try:
		# returns 201 (created)
		send_command(conn, "vms/{}/set_power_state".format(options["--plug"], action), "POST", action, 201)
	except Exception as e:
		logging.debug("Failed: {}".format(e))
		fail(EC_STATUS)

def get_list(conn, options):
	outlets = {}

	try:
		#command = "vcenter/vm"
		command = "vms"
		if "--filter" in options:
			command = command + "?" + options["--filter"]
		res = send_command(conn, command)
	except Exception as e:
		logging.debug("Failed: {}".format(e))
		fail(EC_STATUS)

	for r in res["entities"]:
		outlets[r["uuid"]] = (r["name"], state[r["power_state"]])

	return outlets

def connect(opt):
	conn = pycurl.Curl()

	## setup correct URL
	if "--ssl-secure" in opt or "--ssl-insecure" in opt:
		conn.base_url = "https:"
	else:
		conn.base_url = "http:"

	conn.base_url += "//" + opt["--ip"] + ":" + str(opt["--ipport"]) + opt["--api-path"] + "/"

	## send command through pycurl
	conn.setopt(pycurl.HTTPHEADER, [
		"Accept: application/json",
		"Content-Type: application/json",
		"cache-control: no-cache",
	])

	conn.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_BASIC)
	conn.setopt(pycurl.USERPWD, opt["--username"] + ":" + opt["--password"])

	conn.setopt(pycurl.TIMEOUT, int(opt["--shell-timeout"]))

	if "--ssl-secure" in opt:
		conn.setopt(pycurl.SSL_VERIFYPEER, 1)
		conn.setopt(pycurl.SSL_VERIFYHOST, 2)
	elif "--ssl-insecure" in opt:
		conn.setopt(pycurl.SSL_VERIFYPEER, 0)
		conn.setopt(pycurl.SSL_VERIFYHOST, 0)

	return conn

def disconnect(conn):
	conn.close()

def send_command(conn, command, method="GET", action=None, expected_rc=200):
	url = conn.base_url + command

	conn.setopt(pycurl.URL, url.encode("ascii"))

	web_buffer = io.BytesIO()

	if method == "GET":
		conn.setopt(pycurl.POST, 0)
	if method == "POST":
		conn.setopt(pycurl.POSTFIELDS, action)
	if method == "DELETE":
		conn.setopt(pycurl.CUSTOMREQUEST, "DELETE")

	conn.setopt(pycurl.WRITEFUNCTION, web_buffer.write)

	try:
		conn.perform()
	except Exception as e:
		raise(e)

	rc = conn.getinfo(pycurl.HTTP_CODE)
	result = web_buffer.getvalue().decode("UTF-8")

	web_buffer.close()

	if len(result) > 0:
		result = json.loads(result)

	if rc != expected_rc:
		logging.debug("rc: {}, result: {}".format(rc, result))
		if len(result) > 0:
			raise Exception("{}: {}".format(rc, 
					result))
		else:
			raise Exception("Remote returned {} for request to {}".format(rc, url))

	logging.debug("url: {}".format(url))
	logging.debug("method: {}".format(method))
	logging.debug("response code: {}".format(rc))
	logging.debug("result: {}\n".format(result))

	return result

def define_new_opts():
	all_opt["api_path"] = {
		"getopt" : ":",
		"longopt" : "api-path",
		"help" : "--api-path=[path]              The path part of the API URL",
		"default" : "/PrismGateway/services/rest/v2.0",
		"required" : "0",
		"shortdesc" : "The path part of the API URL",
		"order" : 2}
	all_opt["filter"] = {
		"getopt" : ":",
		"longopt" : "filter",
		"help" : "--filter=[filter]              Filter to only return relevant VMs"
			 " (e.g. \"filter.names=node1&filter.names=node2\").",
		"required" : "0",
		"shortdesc" : "Filter to only return relevant VMs.",
		"order" : 2}


def main():
	device_opt = [
		"ipaddr",
		"api_path",
		"login",
		"passwd",
		"ssl",
		"notls",
		"web",
		"port",
		"filter",
	]

	atexit.register(atexit_handler)
	define_new_opts()

	all_opt["shell_timeout"]["default"] = "5"
	all_opt["power_wait"]["default"] = "1"

	options = check_input(device_opt, process_input(device_opt))

	docs = {}
	docs["shortdesc"] = "Fence agent for Nutanix REST API"
	docs["longdesc"] = """fence_nutanix is an I/O Fencing agent which can be \
used with Nutanix API to fence virtual machines."""
	docs["vendorurl"] = "https://www.nutanix.com"
	show_docs(options, docs)

	####
	## Fence operations
	####
	run_delay(options)

	conn = connect(options)
	atexit.register(disconnect, conn)

	result = fence_action(conn, options, set_power_status, get_power_status, get_list)

	sys.exit(result)

if __name__ == "__main__":
	main()
