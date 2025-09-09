import os
import requests
import xml.etree.ElementTree as ET
import time
import logging
from datetime import datetime
import configparser
import mysql.connector
import pytz  # Import pytz for time zone conversion

logging.basicConfig(
    level=logging.DEBUG,  # show everything
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Config ---
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sfcnc.ini')
config.read(config_path)
logging.debug("DB config loaded: %s", dict(config['database']))

# --- Database setup ---
db_cursor = None
db_connection = None

for machine_name in config.sections():
    if machine_name != 'database':
        CNC_IP = config.get(machine_name, 'CNC_IP')
        CNC_PORT = config.getint(machine_name, 'CNC_PORT', fallback=8082)
        MACHINE_type = config.get(machine_name, 'MACHINE_type')
        table_name = config.get(machine_name, 'table', fallback=f'sfcnc{machine_name[-2:]}')

        url = f"http://{CNC_IP}:{CNC_PORT}/{MACHINE_type}/current"
        logging.info(f"Polling {machine_name} → {url}")

        try:
            response = requests.get(url, timeout=5)
            logging.info(f"{machine_name} responded with {response.status_code}")
        except Exception as e:
            logging.error(f"Failed to reach {machine_name} at {url}: {e}")

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

def convert_boolean(value):
    """Convert string boolean-like values to integer."""
    if value.lower() in ['true', '1']:
        return 1
    elif value.lower() in ['false', '0']:
        return 0
    return value  # Return as is if not a boolean-like string

try:
    db_config = config['database']
    db_connection = mysql.connector.connect(
        user=db_config['username'],
        password=db_config['password'],
        host=db_config['host'],
        port=db_config.getint('port', fallback=3306),
        database=db_config['database']
    )
    db_cursor = db_connection.cursor()

    while True:
        for machine_name in config.sections():
            if machine_name == 'database':
                continue

            CNC_IP = config.get(machine_name, 'CNC_IP')
            CNC_PORT = config.getint(machine_name, 'CNC_PORT', fallback=8082)
            MACHINE_type = config.get(machine_name, 'MACHINE_type')
            table_name = config.get(machine_name, 'table', fallback=f'sfcnc{machine_name[-2:]}')

            url = f"http://{CNC_IP}:{CNC_PORT}/{MACHINE_type}/current"
            logging.info(f"Polling {machine_name} → {url}")

            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    logging.info(f"{machine_name} responded with 200")
                    root = ET.fromstring(response.content)
                    namespace = {"mt": "urn:mtconnect.org:MTConnectStreams:1.2"}

                    extracted_values = {}
                    for message, xpath_query in specific_messages_xpaths.items():
                        elements = root.findall(xpath_query, namespace)
                        value = elements[0].text if elements else None
                        extracted_values[message] = convert_boolean(value) if message != 'RtcpEnabled' else value

                    now_utc = datetime.now(pytz.utc)
                    values = [now_utc] + [extracted_values.get(col, None) for col in column_titles[1:]]

                    sql = f"INSERT INTO {table_name} ({', '.join(column_titles)}) VALUES ({', '.join(['%s']*len(column_titles))})"
                    logging.debug("Preparing SQL: %s", sql)
                    logging.debug("Values: %s", values)

                    try:
                        db_cursor.execute(sql, values)
                        db_connection.commit()
                        logging.info(f"✅ Data inserted into {table_name} table for {machine_name}")
                    except mysql.connector.Error as err:
                        logging.error(f"❌ Error inserting data into {table_name}: {err}")

                else:
                    logging.warning(f"Failed to fetch data for {machine_name}. Status code: {response.status_code}")

            except Exception as e:
                logging.error(f"Error for {machine_name}: {e}")

        time.sleep(15)

except KeyboardInterrupt:
    print("Process interrupted by user.")
finally:
    # Close database connection
    if db_cursor:
        db_cursor.close()
    if db_connection:
        db_connection.close()
