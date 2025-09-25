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
    if value is None:
        return None
    if value.lower() in ['true', '1']:
        return 1
    elif value.lower() in ['false', '0']:
        return 0
    return value  # Return as is if not a boolean-like string

try:
    logging.info("Script started")

    # Initialize DB variables
    db_connection = None
    db_cursor = None

    # Load database config
    db_config = config['database']

    # Attempt to connect to MySQL
    try:
        db_connection = mysql.connector.connect(
            user=db_config['username'],
            password=db_config['password'],
            host=db_config['host'],
            port=db_config.getint('port', fallback=3306),
            database=db_config['database'],
            ssl_disabled=True
        )
        db_cursor = db_connection.cursor()
        logging.debug("DB config loaded: %s", dict(db_config))
        logging.info("Database connection established successfully.")
    except mysql.connector.Error as err:
        logging.error(f"DB connection failed: {err}")
        raise
    except Exception as e:
        logging.error(f"Unexpected DB error: {e}")
        raise

    # Main data gathering loop
    while True:
        for machine_name in config.sections():
            if machine_name == 'database':
                continue

            CNC_IP = config.get(machine_name, 'CNC_IP')
            CNC_PORT = config.getint(machine_name, 'CNC_PORT', fallback=8082)
            MACHINE_type = config.get(machine_name, 'MACHINE_type')
            table_name = config.get(machine_name, 'table', fallback=f'sfcnc{machine_name[-2:]}')

            url = f"http://{CNC_IP}:{CNC_PORT}/{MACHINE_type}/current"
            logging.info(f"Gathering data from {machine_name} → {url}")

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

                    # --- Insert into per-machine table ---
                    sql = f"INSERT INTO {table_name} ({', '.join(column_titles)}) VALUES ({', '.join(['%s']*len(column_titles))})"
                    try:
                        db_cursor.execute(sql, values)
                        db_connection.commit()
                        logging.info(f"✅ Data inserted into {table_name} for {machine_name}")
                    except mysql.connector.Error as err:
                        logging.error(f"❌ Error inserting into {table_name}: {err}")

                    # --- Insert into historical table ---
                    hist_columns = ["MachineName"] + column_titles
                    hist_values = [machine_name] + values
                    hist_sql = f"INSERT INTO cnc_historical ({', '.join(hist_columns)}) VALUES ({', '.join(['%s']*len(hist_columns))})"
                    try:
                        db_cursor.execute(hist_sql, hist_values)
                        db_connection.commit()
                        logging.info(f"📦 Historical row inserted for {machine_name}")
                    except mysql.connector.Error as err:
                        logging.error(f"❌ Error inserting into cnc_historical: {err}")

                    # --- Prune old history (>7 days) ---
                    prune_sql = """
                        DELETE FROM cnc_historical
                        WHERE Timestamp < (NOW() - INTERVAL 7 DAY)
                    """
                    try:
                        db_cursor.execute(prune_sql)
                        db_connection.commit()
                        logging.debug("🧹 Historical table pruned to last 7 days")
                    except mysql.connector.Error as err:
                        logging.error(f"Error pruning historical table: {err}")

                else:
                    logging.warning(f"Failed to fetch data for {machine_name}. Status code: {response.status_code}")

            except Exception as e:
                logging.error(f"Error fetching data for {machine_name}: {e}")

        # Wait before next loop
        time.sleep(15)

except KeyboardInterrupt:
    print("Process interrupted by user.")

finally:
    if db_cursor:
        db_cursor.close()
    if db_connection:
        db_connection.close()
    logging.info("Database connection closed.")
