"""
    Author:
        Amuria

    Description:
        Console based tempus map downloader; downloads missing maps from
        the tempus website directly into your maps folder auto-magically!
        Also works with custom map lists!
"""
from bz2 import BZ2File
import os
import re
import difflib
import shutil
import subprocess
import sys
import winreg
import logging

import requests
from tqdm import tqdm

MAPS_LIST = []
DOWNLOAD_URL = 'https://static.tempus2.xyz/tempus/server/maps/'
GET_MAPS_URL = "https://tempus2.xyz/api/v0/maps/list"
STEAM_TO_MAPS_PATH = "steamapps\\common\\Team Fortress 2\\tf\\download\\maps"

logging.basicConfig(level=logging.INFO,
                    format='%(message)s')


def get_maps_list():
    try:
        response = requests.get(GET_MAPS_URL)
        if response.status_code != 200:
            raise Exception(f"Error: {response.status_code}")

        data = response.json()
        return [element['name'] for element in data]
    except requests.RequestException:
        logging.info((
            "* Error getting maps list from the tempus website\n"
            "* Attempting to use local maps_backup_DATE.txt file\n"
        ))

        try:
            with open("OPTIONAL_maps_backup.txt", 'r') as file:
                MAPS_LIST = [line.strip() for line in file.readlines()]

            logging.info("Maps backup file read successfully!")
            return MAPS_LIST

        except FileNotFoundError:
            logging.critical("Backup File not found")
            logging.critical("You can only input custom lists\n")
            return []


def download_map(name, download_folder, max_size_megabyes=1024):
    URL = f'{DOWNLOAD_URL}/{name}.bsp.bz2'

    if not os.path.exists(download_folder):
        logging.critical("Download folder doesn't exist anymore?! 0_0")
        raise RuntimeError()

    compressed_file_path = os.path.join(download_folder, f'{name}.tmp')
    decompressed_file_path = os.path.join(download_folder, f'{name}.bsp')

    try:
        # Check the size of the file with a HEAD request
        head_response = requests.head(URL)
        head_response.raise_for_status()

        map_size_bytes = int(head_response.headers.get('Content-Length', 0))
        map_size_megabytes = map_size_bytes / (1024 * 1024)

        if map_size_megabytes > max_size_megabyes:
            logging.info(f"{name} is too large - {map_size_megabytes:.1f}M")
            return

        # Download map
        response = requests.get(URL, stream=True)
        response.raise_for_status()

        progress_bar = tqdm(
            total=map_size_bytes,
            unit='B',
            unit_scale=True,
            desc=f"Downloading {name}.bsp.bz2",
            ncols=90
        )

        with open(compressed_file_path, 'wb') as compressed_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    compressed_file.write(chunk)
                    progress_bar.update(len(chunk))

        progress_bar.close()

        # Decompress the file
        with BZ2File(compressed_file_path, 'rb') as compressed_file, \
                open(decompressed_file_path, 'wb') as decompressed_file:
            shutil.copyfileobj(compressed_file, decompressed_file)

        # Clean up
        os.remove(compressed_file_path)
        decompressed_file_path_megabytes = os.path.getsize(
            decompressed_file_path) / (1024 * 1024)
        logging.info((
            f'Downloaded: {name}.bsp - '
            f'final size: {decompressed_file_path_megabytes:.1f}M'
        ))

    except requests.RequestException as e:
        logging.error(f'Error downloading file: {e}')
    except OSError as e:
        logging.error(f'Error decompressing file: {e}')


def get_steam_path_windows():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"
        )
        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
        return install_path

    except FileNotFoundError:
        return None


def get_tf2_maps_folder_path():
    steam_path = get_steam_path_windows()

    if not steam_path:
        logging.error("* Steam directory not found")
        return None

    maps_directory = os.path.join(steam_path, STEAM_TO_MAPS_PATH)
    if os.path.exists(maps_directory):
        logging.info(f"Path found: {maps_directory}")
        return maps_directory

    # Check in other libraries from libraryfolders.vdf
    library_file_path = os.path.join(
        steam_path, "steamapps\\libraryfolders.vdf")

    if os.path.exists(library_file_path):
        with open(library_file_path, 'r') as file:
            content = file.read()
            path_pattern = re.compile(r'"path"\s+"([^"]+)"')
            paths = path_pattern.findall(content)

            for path in paths:
                maps_directory = os.path.join(path, STEAM_TO_MAPS_PATH)
                if os.path.exists(maps_directory):
                    logging.info(f"Path found: {maps_directory}")
                    return maps_directory


def clean_tmp(maps_directory):
    for map_file in os.listdir(maps_directory):
        map_name, map_extension = os.path.splitext(map_file)
        if map_name in MAPS_LIST and map_extension == '.tmp':
            logging.info((
                f"\nWARN: Seems you didn't let the downloader finish "
                f"last time around, removing corrupted map "
                f"({map_name})\n"
            ))
            tmp_file_path = os.path.join(maps_directory, map_file)
            os.remove(tmp_file_path)

            bsp_file_path = os.path.join(maps_directory, f'{map_name}.bsp')
            if os.path.exists(bsp_file_path):
                os.remove(bsp_file_path)


def get_string_array():
    print((
        "\nPlease input a list of map names separated by a comma"
        "\n  Example: jump_beef, conc_concept, jump_psycho"
        "\n\nINFO: Existing maps from the list will not be re-downloaded\n"
        "INFO: Map names do NOT have to match perfectly\n"
    ))
    user_input = input("Enter List >> ")

    # Remove any unnecessary spaces and split by comma
    cleaned_input = user_input.replace('"', '').replace("'", '').strip()
    return [s.strip() for s in cleaned_input.split(',')]


def map_name_find_best_match(map_name, maps_list):
    if map_name in maps_list:
        return map_name

    close_matches = difflib.get_close_matches(
        map_name, maps_list, n=5, cutoff=0.5)

    if not close_matches:
        return None

    # If multiple close matches, let the user choose
    print(f"\n'{map_name}' did you mean:")
    for i, match in enumerate(close_matches, 1):
        print(f"{i}: {match}")

    while True:
        choice = input("Select the map or press Enter to skip: ")
        if choice.isdigit() and 1 <= int(choice) <= len(close_matches):
            return close_matches[int(choice) - 1]
        elif choice == "":
            return None
        else:
            print("Invalid input, try again.")


if __name__ == '__main__':
    maps_directory = get_tf2_maps_folder_path()

    # If fail, set manually
    if not maps_directory:
        logging.error("* Couldn't find the Team Fortress 2 maps folder\n\
                      * Paste your maps folder path manually")
        logging.error(
            r'    Example Path:"\
            C:\SteamLibrary\steamapps\common\Team Fortress 2\tf\download\maps\
                "')

        while 1:
            maps_directory = input(">> ")

            # Idiot proofing
            maps_directory = maps_directory.strip().strip('"').strip("'")

            if os.path.exists(maps_directory):
                break
            else:
                logging.warning("* Path invalid, try again")

    MAPS_LIST = get_maps_list()

    clean_tmp(maps_directory)

    downloaded_maps_list = []
    tempus_maps_size_b = 0
    map_dir_size_b = 0

    # Scan maps folder
    for map_file in os.listdir(maps_directory):
        map_file_path = os.path.join(maps_directory, map_file)

        # Add map size to folder size
        map_dir_size_b += os.path.getsize(map_file_path)

        # Process if Tempus map
        map_name, map_extension = os.path.splitext(map_file)
        if map_name in MAPS_LIST:
            downloaded_maps_list.append(map_name)
            tempus_maps_size_b += os.path.getsize(map_file_path)

    # Calculate what maps will be downloaded
    missing_maps = [
        item for item in MAPS_LIST if item not in downloaded_maps_list]

    # Convert folder size to Gigabytes
    map_dir_size_gb = map_dir_size_b / (1024**3)
    tempus_maps_size_gb = tempus_maps_size_b / (1024**3)
    jump_maps_ratio = (tempus_maps_size_b / map_dir_size_b) * 100

    # Display main Menu
    print("------------------------------------------------------------------")
    print("|                    Custom map folder Analysis:                 |")
    print("------------------------------------------------------------------")
    print(f"* Folder size:  {map_dir_size_gb:.2f} GB")
    print(f"    Jump maps:  {map_dir_size_gb:.2f} GB ({jump_maps_ratio:.0f}%)")
    print()
    print(f"* Total maps: {len(MAPS_LIST)}")
    print(f"   installed: {len(downloaded_maps_list)}")
    print(f"     missing: {len(MAPS_LIST) - len(downloaded_maps_list)}")
    print("------------------------------------------------------------------")

    print("1. Download missing maps")
    print("2. Download missing maps, of size less than 100MB")
    print("3. Download missing maps, of size less than 50MB")
    print("4. Download missing maps, of size less than 20MB")
    print()
    print("5. Download missing map(s) from a custom list")
    print("6. Open maps folder")
    print("7. Exit")
    print()

    # Get user input
    user_input = ''
    map_size_limit_mb = 1024
    while 1:
        user_input = input(">> ")

        if user_input == '2':
            map_size_limit_mb = 100
            break
        elif user_input == '3':
            map_size_limit_mb = 50
            break

        elif user_input == '4':
            map_size_limit_mb = 20
            break

        elif user_input == '5':
            # Get and process the custom input
            custom_maps_list = []
            user_maps = get_string_array()
            for user_string in user_maps:
                best_match = map_name_find_best_match(user_string, MAPS_LIST)
                if best_match:
                    custom_maps_list.append(best_match)
                else:
                    print(f"No match found for '{user_string}', skipping...")

            missing_maps = [
                item for item in missing_maps if item in custom_maps_list]

            if len(missing_maps) == 0:
                print("None of the maps in the list are missing, exiting...")
                sys.exit()

            break

        elif user_input == '7':
            sys.exit()

        # ATTENTION : OUT OF ORDER #
        elif user_input == '6':
            fixed_dir = corrected_path = maps_directory.replace('\\\\', '\\')
            subprocess.run(['explorer', fixed_dir])

        else:
            print("Invalid input")
            print()

    # Warning
    print()
    print("------------------------------------------------------------------")
    print("|                   ~~~~~~ WARNING: ~~~~~~                       |")
    print("|        Exiting mid download will corrupt the current map       |")
    print("|             please START THE TOOL AGAIN to fix it              |")
    print("------------------------------------------------------------------")
    print()

    # Download Maps
    for missing_map in missing_maps:
        download_map(missing_map, maps_directory, map_size_limit_mb)
