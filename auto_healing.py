import time
import sys

from utils_library import *


class EventTrigger(threading.Thread):
    """
        This handles every NETCONF notifications as individual Event so that sooner the Event happens, required
        processing can be triggered using Event-Driven Programming (Call-back style)

        Each of NETCONF notification event handled as separate Thread so that improves Reliability of not missing
        any of NETCONF notifications

        Semaphore used to limit maximum threads at a time so that during Network Chaos, possibility of lof of
        NETCONF notification events triggered on which Central host CPU's not taking hit

        Thread Safe dictionary object used for common access across NETCONF notification events which required to
        analyze Past Events in-case of needing Multi-Criteria verifications
    """
    def __init__(self, device, device_dc, stream, max_threads=10):
        super().__init__()
        self.device = device
        self.device_dc = device_dc
        self.stop_event = threading.Event()
        self.semaphore = threading.Semaphore(max_threads)
        self.stream = stream

        self.thread_safe_dict = ThreadSafeDict()

        # Subscribe for NETCONF notifications for Events
        self.device.nc_con.create_subscription(stream_name=self.stream)

    def run(self):
        # continuously in loop monitor for new NETCONF notifications till thread stopped
        while not self.stop_event.is_set():
            nc_rpc_reply = self.device.nc_con.take_notification()

            # Trigger the callback in a separate thread with semaphore
            run_callback_in_thread(self.device, self.device_dc, nc_rpc_reply, self.thread_safe_dict, self.semaphore)

    def stop(self):
        self.stop_event.set()


# Function to run the callback in a separate thread
def run_callback_in_thread(device, device_dc, nc_rpc_reply, thread_safe_dict, semaphore):
    """
        this helps each of callback to process NETCONF notification event as separate Thread
    """

    callback_thread = threading.Thread(target=auto_healing, args=(device, device_dc, nc_rpc_reply,
                                                                  thread_safe_dict, semaphore))
    callback_thread.start()


# Define the callback function to be run in a separate thread
def auto_healing(device, device_dc, nc_rpc_reply, thread_safe_dict, semaphore):
    """
        This is core function handling auto-healing as below,
            1)  Detect the issue by processing current NETCONF notification event and as required also previous one
            2)  Auto-heal by applying the fix if known defined scenarios

        Note:  This is expandable to include more Scenarios under same category(bgp) or across new categories ospf etc
    """

    with (semaphore):
        nc_rpc_reply_xml = nc_rpc_reply.notification_xml

        # Parse the XML data using xmltodict- this will create an OrderedDict object
        nc_reply_dict = xmltodict.parse(nc_rpc_reply_xml)

        try:
            event_type = nc_reply_dict['notification']['clogMessageGenerated']['object-1']['clogHistFacility']
            event_info = nc_reply_dict['notification']['clogMessageGenerated']['object-4']['clogHistMsgText']
            message = (
                f"{threading.current_thread().name} / #{threading.active_count()} : "
                f"    NETCONF_NOTIFICATION : {event_type:^18} -- {event_info:<20}"
            )
            print(message)

            # This dict data-structure helps populate NETCONF interested notifications to process Multi Criteria..
            # Make sure efficient lookup dict O(1) by keeping relevant info as dict KEY
            if event_type == 'IP':
                event_type = nc_reply_dict['notification']['clogMessageGenerated']['object-3']['clogHistMsgName']

            thread_safe_dict.set_item(event_type, event_info)

            # process current event and also as required check relevant Multiple Criteria to execute Auto-healing
            if event_type == 'BGP':
                match event_info:
                    case _ if re.match(r'neighbor [0-9.]+ Down', event_info):
                        message = (
                            f"{threading.current_thread().name} / #{threading.active_count()} : "
                            f"    LOG : <processing> netconf_notification : BGP neighbor down"
                        )
                        print(message)

                        # check if any already Duplicate IP notification from NETCONF
                        if thread_safe_dict.contains_item('DUPADDR'):
                            message = (
                                f"{threading.current_thread().name} / #{threading.active_count()} : "
                                f"    LOG : --- --- --- --- AUTO_HEALING in-progress... --- --- --- ---"
                            )
                            print(message)

                            mg_1 = re.match(r'neighbor ([0-9.]+) Down', event_info)
                            mg_2 = re.match(r'Duplicate address ([0-9.]+) on (.*), sourced by ',
                                            thread_safe_dict.get_item('DUPADDR'))

                            if mg_1.groups()[0] == mg_2.groups()[0]:
                                ip_format = eval(f'device_dc.{mg_2.groups()[1]}_ip')
                                mask_format = eval(f'device_dc.{mg_2.groups()[1]}_mask')

                                device.edit_config_interface(interface=mg_2.groups()[1],
                                                         ip_address=ip_format,
                                                         mask=mask_format)

                            # Verify Auto-healing actually fixed it..
                            loop_ctrl = 0
                            while loop_ctrl < 20:
                                if device.verify_bgp_mib():
                                    message = (
                                        f"{threading.current_thread().name} / #{threading.active_count()} : "
                                        f"    LOG : --- --- --- --- AUTO_HEALING attempt success --- --- --- ---"
                                    )
                                    print(message)
                                    break

                                loop_ctrl += 1
                                time.sleep(1)

                            if loop_ctrl == 20:
                                message = (
                                    f"{threading.current_thread().name} / #{threading.active_count()} : "
                                    f"    LOG : --- --- --- --- AUTO_HEALING attempt failed --- --- --- ---"
                                )
                                print(message)

                    # here, can expand Auto Healing to cover for more BGP cases
                    case 'add more':
                        print('more')

            # here, can expand Auto Healing to cover for more protocols etc..
            # importantly, if we handle directly event 'DUPADDR' we can reduce down-time a lot because BGP takes
            # approx 180 seconds by default to detect fault without special configs like BFD enabled so blackhole trafic
            if event_type == 'DUPADDR':
                match event_info:
                    case 'xxx xx':
                        print('do')

        except KeyError:
            # Multi level Nested dictionary from XML and safe to skip not-interested Events
            pass


# Main function to set up the event trigger
def main():
    """
        This is main function which do initial setup based on details of MySQL database for Single Source-of-Truth
        This connects to all devices in Topology and also verifies the Baseline initial setup state before monitoring
            for issues to auto-heal part of continuous loop so that it keeps track & take care continuous auto-healing..
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

    # For Auto healing, create an event trigger for interested NETCONF streams example: "NETCONF" stream..
    R1_event_trigger_snmpevents = EventTrigger(R1, R1_DC, 'snmpevents', 10)
    R1_event_trigger_snmpevents.start()

    # Main thread continues to do any other parallel tasks as required..
    try:
        while True:
            print(f"{threading.current_thread().name}...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping event trigger...")
        R1_event_trigger_snmpevents.stop()
        R1_event_trigger_snmpevents.join()


if __name__ == "__main__":
    main()