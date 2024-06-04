import sys
import time

from utils_library import *


def main():
    """
        This is for Brownfield deployment which works as below,
            1) Based on required action like "ospf_enable", "ospf_disable" etc it execute relevant config (or) un-config
                by using NETCONF
            2) This also ensures Baseline verifications before and after required action initiated to verify Topology is
                in stable condition not impacted by Brownfield deployment changes

            Note: This is expandable by adding more cases like "mpls_enable", "mpls_disable" etc
    """

    # Connect to Database for Single Source of Truth
    DB = Database(ip='localhost', username=sys.argv[1], password=sys.argv[2])

    R1_DC = DB.fetch_by_device('R1')
    # R2_DC = DB.fetch_by_device('R2')

    # Connect to Routers of topology
    R1 = Device(ip=R1_DC.mgmt_ip, username=R1_DC.user_name, password=R1_DC.password)
    # R2 = Device(ip=R2_DC.mgmt_ip, username=R2_DC.user_name, password=R2_DC.password)

    # Verify the Baseline health of topology
    if not verify_baseline_health(R1):
        print("Topology devices not per expected Baselines..")
        sys.exit(0)

    action = 'ospf_enable'

    match action:
        case 'ospf_enable':
            # Deploy OSPF on existing topology
            R1.edit_config_ospf(process_id='10',
                                router_id='1.1.1.1',
                                network_ip='19.1.0.0', network_mask='0.0.0.255',
                                area_id='0',
                                action='enable')

        case 'ospf_disable':
            # Remove OSPF from existing topology
            R1.edit_config_ospf(process_id='10',
                                router_id='1.1.1.1',
                                network_ip='19.1.0.0', network_mask='0.0.0.255',
                                area_id='0',
                                action='disable')

        case 'xxx_enable':
            # can be expanded easily adding more cases..
            pass

    # Verify the Baseline health of topology
    # time.sleep(7)
    if not verify_baseline_health(R1):
        print("LOG : FAILED: Topology devices not per expected Baselines after Brownfield deployment changes..")
    else:
        print("LOG : SUCCESS: Topology devices as per expected Baselines after Brownfield deployment changes..")


if __name__ == "__main__":
    main()