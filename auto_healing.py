import threading
import re
import time
import sys

from utils_library import *


class EventTrigger(threading.Thread):
    def __init__(self, device, device_DC, stream, max_threads):
        super().__init__()
        self.device = device
        self.device_DC = device_DC
        self.stop_event = threading.Event()
        self.semaphore = threading.Semaphore(max_threads)
        self.stream = stream

        self.thread_safe_dict = ThreadSafeDict()

        # Subscribe for NETCONF notifications for Events
        # *** --> *** check this for success and accordingly fail with errors
        self.device.nc_con.create_subscription(stream_name=self.stream)

    def run(self):
        while not self.stop_event.is_set():

            nc_rpc_reply = self.device.nc_con.take_notification()

            # Trigger the callback in a separate thread with semaphore
            run_callback_in_thread(self.device, self.device_DC, nc_rpc_reply, self.thread_safe_dict, self.semaphore)

    def stop(self):
        self.stop_event.set()


# Function to run the callback in a separate thread
def run_callback_in_thread(device, device_DC, nc_rpc_reply, thread_safe_dict, semaphore):
    callback_thread = threading.Thread(target=callback_function, args=(device, device_DC, nc_rpc_reply,
                                                                       thread_safe_dict, semaphore))
    callback_thread.start()


# Define the callback function to be run in a separate thread
def callback_function(device, device_DC, nc_rpc_reply, thread_safe_dict, semaphore):
    with semaphore:
        # print(f"Callback function invoked with data: {nc_rpc_reply}")

        nc_rpc_reply_xml = nc_rpc_reply.notification_xml
        # print(nc_rpc_reply_xml)

        # Parse the XML data using xmltodict- this will create an OrderedDict object
        nc_reply_dict = xmltodict.parse(nc_rpc_reply_xml)
        # print(nc_reply_dict)

        try:

            event_type = nc_reply_dict['notification']['clogMessageGenerated']['object-1']['clogHistFacility']
            event_info = nc_reply_dict['notification']['clogMessageGenerated']['object-4']['clogHistMsgText']
            message = (
                f"{threading.current_thread().name}: "
                f"*** NETCONF_NOTIFICATION : {event_type:^25} -- {event_info:<20}"
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
                            f"{threading.current_thread().name}: "
                            f"### LOG : <processing> netconf_notification : BGP neighbor down"
                        )
                        print(message)

                        # check if any already Duplicate IP notification from NETCONF
                        if thread_safe_dict.contains_item('DUPADDR'):
                            message = (
                                f"{threading.current_thread().name}: "
                                f"### LOG : --- --- --- --- AUTO_HEALING in-action... --- --- --- ---"
                            )
                            print(message)

                            mg_1 = re.match(r'neighbor ([0-9.]+) Down', event_info)
                            mg_2 = re.match(r'Duplicate address ([0-9.]+) on (.*), sourced by ',
                                            thread_safe_dict.get_item('DUPADDR'))

                            if mg_1.groups()[0] == mg_2.groups()[0]:

                                ip_format = eval(f'device_DC.{mg_2.groups()[1]}_ip')
                                mask_format = eval(f'device_DC.{mg_2.groups()[1]}_mask')

                                device.edit_config_interface(interface=mg_2.groups()[1],
                                                         ip_address=ip_format,
                                                         mask=mask_format)

                    # here, can expand Auto Healing to cover for more BGP cases
                    case 'add more':
                        print('more')

            # here, can expand Auto Healing to cover for more protocols etc..
            # importantly, if we handle directly event 'DUPADDR' we can reduce down-time a log because BGP takes
            # approx 180 seconds to detect fault without special configs like BFD enabled
            if event_type == 'DUPADDR':
                match event_info:
                    case 'xxx xx':
                        print('do')

            # print(nc_reply_dict['notification'])
            # thread_safe_dict.print_items()

        except KeyError:
            # Multi level Nested dictionary from XML and safe to skip not-interested Events
            pass


# Main function to set up the event trigger
def main():

    # Connect to Database for Single Source of Truth
    DB = Database('localhost')

    R1_DC = DB.fetch_by_device('R1')
    # R2_DC = DB.fetch_by_device('R2')

    # Connect to Routers of topology
    R1 = Device(ip=R1_DC.mgmt_ip, username=R1_DC.user_name, password=R1_DC.password)
    # R2 = Device(ip=R2_DC.mgmt_ip, username=R2_DC.user_name, password=R2_DC.password)

    # Verify the Baseline health of topology
    if not verify_baseline_health(R1):
        print("Topology devices not per expected Baselines..")
        sys.exit(0)

    # For Auto healing, create an event trigger for interested NETCONF streams like "NETCONF"
    # and "snmpevents" etc..
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