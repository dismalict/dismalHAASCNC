#!/bin/bash

# Update package list
#apt-get update

# Install pip if not installed
if ! command -v pip &> /dev/null
then
    echo "pip not found, installing..."
    sudo su
    sudo apt-get install -y python3-pip
fi
sudo su
# install python-is-python3
sudo apt-get install -y python-is-python3
# Install required Python packages
sudo pip3 install mysql-connector-python
sudo pip3 install configparser
sudo pip3 install pytz