import yaml
from jinja2 import Environment, FileSystemLoader


def handle_yaml():
    # Read YAML input file
    with open("GreenField/devices.yaml") as file:
        device_info = yaml.safe_load(file)

    # Read your jinja template file
    env = Environment(
        loader=FileSystemLoader('Greenfield/'),
        trim_blocks=True,
        lstrip_blocks=True
    )
    template = env.get_template('template.j2')

    # iterate over the devices described in your yaml file and use jinja to render your configuration
    for device in device_info["devices"]:
        # write new CONFIG files for each of Routers
        with open(f'GreenField/DHCP_server_upload/{device["name"]}-config', 'w') as file:
            file.write(template.render(device=device["name"], interfaces=device["interfaces"],
                                       logging_snmp_traps=device["logging_snmp_traps"],
                                       snmp_enable_traps=device["snmp_enable_traps"],
                                       netconf_yang_traps=device["netconf_yang_traps"],
                                       bgp_asn=device["bgp_asn"], bgp_neighbors=device["bgp_neighbors"]))


if __name__ == "__main__":
    # generate the CONFIG files of Router of Topology
    handle_yaml()

