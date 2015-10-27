import socket
import os
import os.path
import sys
import re
import traceback
import subprocess
import json
import logging
import logging.handlers
import urllib2
import time

def load_config(config_files):
    """ loads json configuration files
    the latter configs overwrite the previous configs
    """

    config = dict()

    for f in config_files:
        with open(f, 'rt') as cfg:
            config.update(json.load(cfg))

    return config

def lookup_ips(address):
    """ gets all ip addresses for a dns entry """

    try:
        return [a[-1][0] for a in socket.getaddrinfo(address.strip(), 80)]
    except:
        logging.debug("could not resolve '{}'".format(address))

    # return a empty list with an empty element
    return [""]

def ip_version(address):
    """ returns the ip version, can be either 4 or 6 """

    m = re.match("[0-9a-fA-F:]{5}", address)
    if m is not None:
        return 6
    elif re.match("[0-9.]{3}", address):
        return 4

    return None

def get_blacklist(url, timeout):
    """ loads the blacklist from the provided url and returns as string """

    try:
        response = urllib2.urlopen(url, timeout=timeout)
        return response.read()
    except urllib2.URLError:
        logging.warning("Blacklist could not be fetched.")
        return False

def lookup_ipaddresses(domains):
    """ looks up the provided domains and returns a single list of all
    corresponding IP addresses """
    ip_addresses_lists = [lookup_ips(addr.strip()) for addr in domains.split() if addr.strip()]
    return list(set([ip for address_list in ip_addresses_lists for ip in address_list])) 

def get_blacklisted_ipaddresses():
    """ provides the caller with a list of blacklisted ipaddresses that
    are either cached or just retrieved."""
    global config

    if (config["blacklist_cache_path"]
        and os.path.exists(config["blacklist_cache_path"])
        and time.time() - os.path.getmtime(config["blacklist_cache_path"]) < (60 * config["max_cache_duration_in_minutes"])
        ):
        with open(config["blacklist_cache_path"], "r") as f:
            return f.readlines()
    else:
        blacklist = get_blacklist(config["blacklist_url"], config["timeout"])
        addresses = lookup_ipaddresses(blacklist)

        if config["blacklist_cache_path"]:
            with open(config["blacklist_cache_path"], "w") as f:
                for addr in addresses:
                    f.write("{address}\n".format(address = addr))

        return addresses
    

def insert_blacklist_rules(ip_addresses):
    """ inserts the iptables rules to block the provided ip_addresses """
    global config
    for addr in ip_addresses:
        subprocess.call( [config["ip4tables_cmd"] if ":" not in addr else config["ip6tables_cmd"]]
                        + ["-I", config["iptables_chain"], "1", "-d", addr] 
                        + (   ["-s", config["blocked_local_client_address_v4"]] if ":" not in addr and config["blocked_local_client_address_v4"] 
                         else ["-s", config["blocked_local_client_address_v6"]] if ":"     in addr and config["blocked_local_client_address_v6"] 
                         else [])
                        + ["-j", "REJECT"])

def excepthook(excType, excValue, tb):
    """ this function is called whenever an exception is not catched """
    global config
    err = "Uncaught exception:\n{}\n{}\n{}".format(str(excType), excValue, "".join(traceback.format_exception(excType, excValue, tb)))
    logging.error(err)

    # try to notify the sysadmin about this
    try:
        subprocess.call(config["notification_cmd"].format(msg="Error: " + err), shell=true)
    except Exception as inst:
        logging.error("could not notify admin, {}".format(inst))

def main():
    """ main program procedure. it retrieves the blacklisted domains,
    looks them up and inserts the blocking rules. """

    insert_blacklist_rules(get_blacklisted_ipaddresses())


if __name__ == "__main__":
    # configuration
    sys.excepthook = excepthook
    config = load_config(["config.json"])
    log_path = config["log_path"]

    # init logging
    rot_handler = logging.handlers.RotatingFileHandler(log_path, maxBytes=1000000, backupCount=5)
    rot_handler.setFormatter(logging.Formatter('%(levelname)s\t | %(asctime)s | %(message)s'))
    logging.getLogger().addHandler(rot_handler)
    logging.getLogger().addHandler(logging.StreamHandler())
    logging.getLogger().setLevel(logging.DEBUG if config["verbose"] else logging.INFO)

    # run main procedure
    main()


