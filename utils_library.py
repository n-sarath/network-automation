import threading
import re
from dataclasses import dataclass

import mysql.connector
import xmltodict
from ncclient import manager, xml_


@dataclass
class DeviceData:
    """
        Dataclass to handle DATA about Device retrieved from Database as a single record
    """
    host_name: str
    user_name: str
    password: str
    mgmt_ip: str
    GigabitEthernet1_ip: str
    GigabitEthernet1_mask: str
    GigabitEthernet2_ip: str
    GigabitEthernet2_mask: str
    GigabitEthernet4_ip: str
    GigabitEthernet4_mask: str


class Device:
    """
        Handle Device specific like connection, config, operational

        Note: when need to Scale up for multiple scenarios like BGP, OSPF, MPLS it can be easily
        done through Inheritance
    """
    def __init__(self, ip, username, password):
        self.ip = ip
        self.username = username
        self.password = password

        self.nc_port = 830
        self.nc_dev_type = 'iosxe'
        self.nc_con = manager.connect(host=self.ip, port=self.nc_port, username=self.username,
                                      password=self.password, device_params={'name': self.nc_dev_type})

    def get_capabilities(self):
        return self.nc_con.server_capabilities

    def get_config(self):
        return self.nc_con.get_config('running')

    def verify_bgp_mib(self):
        """
            This verifies BGP operational state using NETCONF
        """

        with open('Templates/bgp_oper.xml', 'r') as file:
            netconf_filter = file.read()

        # Make the `<get>` RPC request applying the filter and parse using xmltodict
        nc_rpc_reply = self.nc_con.get(filter=netconf_filter).xml
        nc_reply_dict = xmltodict.parse(nc_rpc_reply)

        session_state = parse_nested_dict(nc_reply_dict, 'rpc-reply', 'data', 'BGP4-MIB',
                                          'bgpPeerTable', 'bgpPeerEntry', 'bgpPeerState')

        return True if session_state == 'established' else False

    def edit_config_interface(self, interface='', ip_address='', mask=''):
        """
            This configures interface with given details using NETCONF
        """

        mg_1 = re.search(r'[A-Za-z]([0-9])', interface)

        # Open template file to read yang model
        with open('Templates/interface_config.xml', 'r') as file:
            config_snippet = file.read()

        # Define the variables which gets variable substitution in the templates file
        variables = {'mg_1_groups_0': mg_1.groups()[0], 'ip_address': ip_address, 'mask_1': mask}
        mg_1_groups_0 = mg_1.groups()[0]
        mask_1 = mask

        # String format approach with dictionary unpacking
        config_snippet = config_snippet.format(**variables)

        # Make the `<get>` RPC edit config the filter
        self.nc_con.edit_config(config=config_snippet, target="running")

    def edit_config_ospf(self, process_id, router_id, network_ip, network_mask, area_id, action):
        """
            This configures OSPF with given details using NETCONF
        """

        # Open template file to read yang model
        with open('Templates/ospf_config.xml', 'r') as file:
            config_snippet = file.read()

        if action == 'disable':
            delete = ' operation="delete"'
        else:
            delete = ''

        # Define the variables which gets variable substitution in the templates file
        variables = {'process_id': process_id, 'router_id': router_id, 'network_ip': network_ip,
                     'network_mask': network_mask, 'area_id': area_id, 'action': delete}

        # String format approach with dictionary unpacking
        config_snippet = config_snippet.format(**variables)

        # Make the `<get>` RPC edit config the filter
        self.nc_con.edit_config(config=config_snippet, target="running")

    def close(self):
        """
            Gracefully close the NETCONF connection
        """
        self.nc_con.close_session()


class Database:
    """
        Handle Database specific like connection, query
    """
    def __init__(self, ip, username, password):
        self.host = ip
        self.user = username
        self.password = password
        self.database = 'ipam_database'
        self.conn = mysql.connector.connect(host=self.host, user=self.user, passwd=self.password,
                                           database=self.database)
        self.cursr = self.conn.cursor()

    def fetch_by_device(self, host_name):
        """
            This fetch the details from database using MySQL Query
        """

        # Query the database
        query = ("SELECT * FROM ipam_db_table WHERE host_name = %s")
        self.cursr.execute(query, (host_name,))

        # Fetch the result
        row = self.cursr.fetchone()

        if row is None:
            return None

        # Populate the Dataclass with list unpacking
        record = DeviceData(*row)

        return record

    def close(self):
        """
            Gracefully close the DATABASE connection
        """
        self.cursr.close()
        self.conn.close()


class ThreadSafeDict:
    """
        As multi-threading implementation during multiple threads access data at same time may conflict, this helps
        safe data access across threads by implementing Locking
    """
    def __init__(self):
        self.dict = {}
        self.lock = threading.Lock()

    def set_item(self, key, value):
        with self.lock:
            self.dict[key] = value

    def get_item(self, key):
        with self.lock:
            return self.dict.get(key)

    def remove_item(self, key):
        with self.lock:
            if key in self.dict:
                del self.dict[key]

    def contains_item(self, key):
        with self.lock:
            if key in self.dict:
                return True

    def print_items(self):
        with self.lock:
            for k, v in self.dict.items():
                print(f"{k:<15} -- {v:<30}")


def verify_baseline_health(device):
    """
        To verify initial Baseline health of topology
    """
    return device.verify_bgp_mib()


def parse_nested_dict(data, *args):
    """
        Handle nested dictionary as being multi-level nested being XML response from NETCONF
    """
    if args and data:
        element = args[0]
        if element:
            value = data.get(element)
            return value if len(args) == 1 else parse_nested_dict(value, *args[1:])


def print_xml(res):
    """
        Handle printing easy readable XML representation of NETCONF response. Pretty print XML
    """
    print(xml_.to_xml(res.data_ele, pretty_print=True))


