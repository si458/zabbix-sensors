#!/usr/bin/env python3

import errno
import json
import re
import os
import sys
import glob

DIR = "/sys/class/hwmon"

def read(fn):
    try:
        with open(fn) as f:
            return f.read()
    except OSError as e:
        # in some cases nouveau might return EINVAL when GPU is not in use
        # We are defaulting to 0 when the value cannot be read
        # https://github.com/torvalds/linux/blob/v6.9/drivers/gpu/drm/nouveau/nouveau_hwmon.c#L379
        if e.errno == errno.EINVAL:
            return '0'
        else:
            raise

def read_parse(fn):
    x = read(fn).strip()
    try:
        return int(x)
    except ValueError:
        return x

def list_hwmon():
    return sorted([f for f in os.listdir(DIR) if f.startswith("hwmon")])

def get_hwmon_name(path):
    name_path = f"{path}/name"
    if os.path.exists(name_path):
        return read(name_path).strip()
    device_name_path = f"{path}/device/name"
    if os.path.exists(device_name_path):
        return read(device_name_path).strip()
    return None

def process_sensors(path):
    r = {}
    
    # Check both root and device paths (device first)
    search_paths = [path]
    device_path = f"{path}/device"
    if os.path.exists(device_path):
        search_paths.insert(0, device_path)
    
    for base_path in search_paths:
        try:
            for fn in os.listdir(base_path):
                # Match sensor files (temp1_input, fan2_min etc)
                m = re.match(r"^(fan|in|temp|power)(\d+)_(.*)$", fn)
                if not m:
                    continue

                sensor_type, sensor_num, reading_type = m.groups()
                sensor_id = f"{sensor_type}{sensor_num}"
                
                # Initialize sensor entry if not exists
                if sensor_id not in r:
                    r[sensor_id] = {"sensor_type": sensor_type}
                    
                    # Check for label file
                    label_file = f"{base_path}/{sensor_type}{sensor_num}_label"
                    if os.path.exists(label_file):
                        r[sensor_id]["label"] = read(label_file).strip()
                
                # Add the reading if not already present
                if reading_type not in r[sensor_id]:
                    r[sensor_id][reading_type] = read_parse(f"{base_path}/{fn}")
                    
        except OSError:
            continue
            
    return r

def process_hwmon(n):
    path = f"{DIR}/{n}"
    name = get_hwmon_name(path)
    if not name:
        return None, None

    # Handle block device naming (original functionality)
    blockdev = False
    device_path = f"{path}/device"
    
    if os.path.isdir(f"{device_path}/block"):
        blockdev = os.path.basename(glob.glob(f"{device_path}/block/*")[0])
    elif os.path.isdir(f"{path}/block"):
        blockdev = os.path.basename(glob.glob(f"{path}/block/*")[0])

    if not blockdev:
        nvme_paths = glob.glob(f"{device_path}/nvme*") or glob.glob(f"{path}/nvme*")
        if nvme_paths:
            blockdev = os.path.basename(nvme_paths[0])

    raw_devlinks = glob.glob("/dev/disk/by-id/*")
    devlinks = list(filter(lambda x: not re.search("^nvme-eui|^nvme-nvme|^wwn-0x|^scsi-[0-9]", os.path.basename(x)), raw_devlinks))
    if blockdev:
        for devlink in devlinks:
            if os.path.islink(devlink) and blockdev == os.path.basename(os.readlink(devlink)):
                name = os.path.basename(devlink)
                break

    return name, process_sensors(path)

def main():
    r = {}

    for hwm in list_hwmon():
        try:
            name, sensors = process_hwmon(hwm)
        except Exception as e:
            sys.stderr.write(f"Failure to process {hwm}: {e}\n")
            continue
        if not sensors:
            continue

        r[name] = sensors

    print(json.dumps(r, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
