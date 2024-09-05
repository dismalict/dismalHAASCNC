import os
import requests
import xml.etree.ElementTree as ET
import time
import logging
from datetime import datetime
import configparser
import mysql.connector
import pytz  # Import pytz for time zone conversion

# Configure the logging module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Script started")

# Define column titles
column_titles = ["Timestamp", "RapidOverride", "LastCycle", "ThisCycle", "CycleRemainingTime",
                 "FeedrateOverride", "SpindleSpeed", "SpindleSpeedOverride",
                 "EmergencyStop", "MachineRunTime", "Mode", "RunStatus",
                 "ActiveAlarms", "MacroDispl1", "LoopsRemaining", "M30Counter2",
                 "M30Counter1", "MacroDispl2", "Program",
                 "TscEnabled", "CoolantSpigotEnabled", "TabEnabled",
                 "HpcEnabled", "ShowerCoolantEnabled", "MistEnabled",
                 "PulseJet", "CompTablesEnabled", "M19SpindleOrientEnabled",
                 "TSCPurchased", "TwpEnabled", "FourthAxisEnabled",
                 "MacroEnabled", "MediaDisplayEnabled", "MaxPurchSpindleSpeed",
                 "RigidTappingEnabled", "WirelessNetworkEnabled", "RotateAndScalingEnabled",
                 "HiSpeedMachiningEnabled", "TcpcDwoEnabled", "RtcpEnabled",
                 "CustomRotariesEnabled", "FifthAxisEnabled", "PolarEnabled",
                 "MaxMemPurchased", "VPSEditEnabled"]

# Define XPath queries
specific_messages_xpaths = {
    "RapidOverride": ".//mt:AxisFeedrate[@name='RapidOverride']",
    "LastCycle": ".//mt:AccumulatedTime[@name='LastCycle']",
    "ThisCycle": ".//mt:AccumulatedTime[@name='ThisCycle']",
    "CycleRemainingTime": ".//mt:AccumulatedTime[@name='CycleRemainingTime']",
    "FeedrateOverride": ".//mt:PathFeedrate[@name='FeedrateOverride']",
    "SpindleSpeed": ".//mt:SpindleSpeed[@name='SpindleSpeed']",
    "SpindleSpeedOverride": ".//mt:SpindleSpeed[@name='SpindleSpeedOverride']",  # Corrected XPath
    "EmergencyStop": ".//mt:EmergencyStop[@name='EmergencyStop']",
    "MachineRunTime": ".//mt:Message[@name='MachineRunTime']",
    "Mode": ".//mt:ControllerMode[@name='Mode']",
    "RunStatus": ".//mt:Execution[@name='RunStatus']",
    "ActiveAlarms": ".//mt:Message[@name='ActiveAlarms']",
    "MacroDispl1": ".//mt:Message[@name='MacroDispl1']",
    "LoopsRemaining": ".//mt:Message[@name='LoopsRemaining']",
    "M30Counter2": ".//mt:Message[@name='M30Counter2']",
    "M30Counter1": ".//mt:Message[@name='M30Counter1']",
    "MacroDispl2": ".//mt:Message[@name='MacroDispl2']",
    "Program": ".//mt:Program[@name='Program']",
}

# Define XPath queries for additional messages
additional_messages_xpaths = {
    "TscEnabled": ".//mt:Message[@name='TscEnabled']",
    "CoolantSpigotEnabled": ".//mt:Message[@name='CoolantSpigotEnabled']",
    "TabEnabled": ".//mt:Message[@name='TabEnabled']",
    "HpcEnabled": ".//mt:Message[@name='HpcEnabled']",
    "ShowerCoolantEnabled": ".//mt:Message[@name='ShowerCoolantEnabled']",
    "MistEnabled": ".//mt:Message[@name='MistEnabled']",
    "PulseJet": ".//mt:Message[@name='PulseJet']",
    "CompTablesEnabled": ".//mt:Message[@name='CompTablesEnabled']",
    "M19SpindleOrientEnabled": ".//mt:Message[@name='M19SpindleOrientEnabled']",
    "TSCPurchased": ".//mt:Message[@name='TSCPurchased']",
    "TwpEnabled": ".//mt:Message[@name='TwpEnabled']",
    "FourthAxisEnabled": ".//mt:Message[@name='FourthAxisEnabled']",
    "MacroEnabled": ".//mt:Message[@name='MacroEnabled']",
    "MediaDisplayEnabled": ".//mt:Message[@name='MediaDisplayEnabled']",
    "MaxPurchSpindleSpeed": ".//mt:Message[@name='MaxPurchSpindleSpeed']",
    "RigidTappingEnabled": ".//mt:Message[@name='RigidTappingEnabled']",
    "WirelessNetworkEnabled": ".//mt:Message[@name='WirelessNetworkEnabled']",
    "RotateAndScalingEnabled": ".//mt:Message[@name='RotateAndScalingEnabled']",
    "HiSpeedMachiningEnabled": ".//mt:Message[@name='HiSpeedMachiningEnabled']",
    "TcpcDwoEnabled": ".//mt:Message[@name='TcpcDwoEnabled']",
    "RtcpEnabled": ".//mt:Message[@name='RtcpEnabled']",
    "CustomRotariesEnabled": ".//mt:Message[@name='CustomRotariesEnabled']",
    "FifthAxisEnabled": ".//mt:Message[@name='FifthAxisEnabled']",
    "PolarEnabled": ".//mt:Message[@name='PolarEnabled']",
    "MaxMemPurchased": ".//mt:Message[@name='MaxMemPurchased']",
    "VPSEditEnabled": ".//mt:Message[@name='VPSEditEnabled']",
}

# Merge additional_messages_xpaths into specific_messages_xpaths
specific_messages_xpaths.update(additional_messages_xpaths)

# Read configuration from .config file
config = configparser.ConfigParser()
config.read('sfcncv.ini')

db_cursor = None
db_connection = None

def convert_boolean(value):
    """Convert string boolean-like values to integer."""
    if value.lower() in ['true', '1']:
        return 1
    elif value.lower() in ['false', '0']:
        return 0
    return value  # Return as is if not a boolean-like string

try:
    # Connect to MySQL database
    db_config = config['database']
    db_connection = mysql.connector.connect(
        user=db_config['username'],
        password=db_config['password'],
        host=db_config['host'],
        port=db_config.getint('port', fallback=3306),
        database=db_config['database']
    )
    db_cursor = db_connection.cursor()

    # Main loop for each machine
    while True:
        for machine_name in config.sections():
            if machine_name != 'database':  # Skip the 'Database' section
                try:
                    # Global variables for the CNC machine's IP and port
                    CNC_IP = config.get(machine_name, 'CNC_IP')
                    CNC_PORT = config.getint(machine_name, 'CNC_PORT', fallback=8082)
                    MACHINE_type = config.get(machine_name, 'MACHINE_type')
                    table_name = config.get(machine_name, 'table', fallback=f'sfcnc{machine_name[-2:]}')  # Extract the last two characters of machine_name

                    # Send a GET request to the MT Connect URL
                    response = requests.get(f"http://{CNC_IP}:{CNC_PORT}/{MACHINE_type}/current")

                    # Check if the request was successful (status code 200)
                    if response.status_code == 200:
                        # Parse the XML content
                        root = ET.fromstring(response.content)
                        logging.info(f"Connection Successful - Data Pulled for {machine_name}")

                        # Register the MT Connect namespace
                        namespace = {"mt": "urn:mtconnect.org:MTConnectStreams:1.2"}

                        # Create a dictionary to store the extracted values
                        extracted_values = {}

                        # Iterate through specific_messages_xpaths and extract values
                        for message, xpath_query in specific_messages_xpaths.items():
                            elements = root.findall(xpath_query, namespace)
                            if elements:
                                value = elements[0].text
                                extracted_values[message] = convert_boolean(value) if message != 'RtcpEnabled' else value
                            else:
                                extracted_values[message] = None  # Explicitly set to None

                        # Convert the current time to UTC
                        now_utc = datetime.now(pytz.utc)

                        # Prepare data for insertion
                        values = [now_utc] + [extracted_values.get(col, None) for col in column_titles[1:]]

                        # Prepare SQL statement
                        sql = f"INSERT INTO {table_name} ({', '.join(column_titles)}) VALUES ({', '.join(['%s'] * len(column_titles))})"

                        try:
                            db_cursor.execute(sql, values)
                            db_connection.commit()
                            logging.info(f"Data inserted into {table_name} table for {machine_name}")
                        except mysql.connector.Error as err:
                            logging.error(f"Error inserting data into {table_name} table: {err}")

                    else:
                        logging.warning(f"Failed to fetch data for {machine_name}. Status code: {response.status_code}")
                except Exception as e:
                    logging.error(f"Error occurred for {machine_name}: {e}")

        # Wait for 15 seconds before fetching data for the next loop
        time.sleep(15)

except KeyboardInterrupt:
    print("Process interrupted by user.")
finally:
    # Close database connection
    if db_cursor:
        db_cursor.close()
    if db_connection:
        db_connection.close()