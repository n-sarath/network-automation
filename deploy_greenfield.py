import yaml
from jinja2 import Environment, FileSystemLoader


def handle_yaml():
    """
        This is for Greenfield deployment which works as below,
            1) Takes input from YAML file for each of Router Configurations
            2) Generate individual Router config files as "hostname-config" at the folder DHCP_server_upload/ so that
                these individual config files to be uploaded to DHCP (or) TFTP server based on Cisco (or) Juniper
                workflow of ZTP/auto-install followed for Day-0 bring-up
    """

    # Read YAML input file
    with open("GreenField/devices.yaml") as file:
        device_info = yaml.safe_load(file)

    # Read Jinja template file
    env = Environment(loader=FileSystemLoader('GreenField/'),
                      trim_blocks=True,
                      lstrip_blocks=True)
    template = env.get_template('template.j2')

    # iterate over the devices described in yaml file and use jinja to render the configuration
    for device in device_info["devices"]:
        # write new CONFIG files for each of Routers at the location DHCP_server_upload/
        with open(f'GreenField/DHCP_server_upload/{device["name"]}-config', 'w') as file:
            file.write(template.render(device=device["name"], interfaces=device["interfaces"],
                                       logging_snmp_traps=device["logging_snmp_traps"],
                                       snmp_enable_traps=device["snmp_enable_traps"],
                                       netconf_yang_traps=device["netconf_yang_traps"],
                                       bgp_asn=device["bgp_asn"], bgp_neighbors=device["bgp_neighbors"]))

    print("LOG : SUCCESS: configuration files generated and please find at DHCP_server_upload/ directory..")


if __name__ == "__main__":
    # generate the CONFIG files of Router of Topology
    handle_yaml()

