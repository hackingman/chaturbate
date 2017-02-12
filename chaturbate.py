#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
This module automatically records shows from your followed models
using rtmpdump.

The requirements are:
 * RTMPDump-ksv - https://github.com/BurntSushi/rtmpdump-ksv
 * BeautifulSoup - https://www.crummy.com/software/BeautifulSoup/
 * requests - http://docs.python-requests.org/en/master/
"""

import os
import sys
if sys.version_info[0] < 3:
    import ConfigParser
    DEVNULL = open(os.devnull, 'wb')
else:
    import configparser
    from subprocess import DEVNULL

import subprocess
import re
import urllib
import time
import json
from datetime import datetime, timedelta
import logging
import requests
from bs4 import BeautifulSoup


class Chaturbate(object):
    """
    Script to record Chaturbate streams.
    """
    agent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36' \
                 '(KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36'
    """User agent to be used in the requests."""
    processes = []
    """A list with all the processes."""
    request = None
    """An instance of the requests class."""
    log = None
    """An instance of the Python logger."""
    config = {
        'username': None,
        'password': None,
        'capturing_path': None,
        'completed_path': None,
        'debug': None,
        'ffmpeg': None,
        'ffmpeg-flags': None,
    }
    """Configuration"""

    def __init__(self):
        """
        Configures logging, reads configuration
        """
        self.detect_rtmpdump()

        # create a requests object with sessions
        self.request = requests.Session()

        # configure logging
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        self.log = logging.getLogger("chaturbate")
        self.log.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                      "%Y-%m-%d %H:%M:%S")
        console_handler.setFormatter(formatter)
        self.log.addHandler(console_handler)

        # read configuration
        config_fn = "config.ini"

        if not os.path.exists(config_fn):
            self.log.error("%s not found", config_fn)
            sys.exit()

        if sys.version_info[0] < 3:
            config = ConfigParser.ConfigParser()
        else:
            config = configparser.ConfigParser()

        config.read(config_fn)

        self.config['username'] = config.get('User', 'username')
        self.config['password'] = config.get('User', 'password')

        self.config['ffmpeg'] = config.get('FFmpeg', 'enable')
        self.config['ffmpeg-flags'] = config.get('FFmpeg', 'options')

        try:
            self.config['debug'] = config.get('Debug', 'enable')
        except ConfigParser.NoSectionError:
            pass

        # Create directories
        self.config['capturing_path'] = config.get('Directories', 'capturing')
        self.config['completed_path'] = config.get('Directories', 'complete')

        self.test_path(self.config['capturing_path'])
        self.test_path(self.config['completed_path'])

    def test_path(self, path):
        """
        Tests if a path exists and if its possible to write to it.

        :param path: Path to test.
        """
        if os.path.isdir(path) is False:
            try:
                os.mkdir(path)
            except OSError:
                self.log.error("Unable to create %s", path)
                sys.exit(1)

        filename = "test-perm.txt"
        filename = os.path.join(path, filename)
        try:
            file_handle = open(filename, 'w')
            file_handle.close()
            os.remove(filename)
        except IOError:
            self.log.error("Unable to write to %s", filename)
            sys.exit(1)

    @staticmethod
    def detect_rtmpdump():
        """
        Checks if rtmpdump-ksv is installed

        :rtype: bool
        """
        arguments = [
            "rtmpdump",
            "--help",
        ]

        output = subprocess.check_output(arguments, stderr=subprocess.STDOUT)

        if b'--weeb' not in output:
            sys.exit("rtmpdump-ksv not detected")


    @staticmethod
    def get_human_size(size):
        """
        Returns file size in a human readable format.

        :param int size: File size in bytes.
        :return: Pretty file size.

        :rtype: str
        """
        suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        if size == 0:
            return '0 B'
        i = 0
        while size >= 1024 and i < len(suffixes) - 1:
            size /= 1024.
            i += 1
        f = ('%.2f' % size).rstrip('0').rstrip('.')
        return '%s %s' % (f, suffixes[i])

    @staticmethod
    def is_logged(html):
        """
        Checks if you're currently logged in.

        :param str html: The HTML source to check.

        :rtype: bool
        """
        soup = BeautifulSoup(html, "html.parser")

        if soup.find('div', {'id': 'user_information'}) is None:
            return False
        return True

    @staticmethod
    def run_rtmpdump(flv_info, output_filename, extra_argument=""):
        """
        Runs rtmpdump with the provided parameters.

        :param list flv_info: A list with all the flv variables.
        :param str output_filename: Filename where to output the stream.
        :param str extra_argument: Extra argument to pass to rtmpdump.

        :return: A Popen object (process).
        :rtype: Popen
        """
        if sys.version_info[0] < 3:
            unquote = urllib.unquote(flv_info[15])
        else:
            unquote = urllib.parse.unquote(flv_info[15])

        arguments = [
            "rtmpdump",
            "--quiet",
            "--live",
            extra_argument,
            "--rtmp", "rtmp://" + flv_info[2] + "/live-edge",
            "--pageUrl", "http://chaturbate.com/" + flv_info[1],
            "--conn", "S:" + flv_info[8],
            "--conn", "S:" + flv_info[1],
            "--conn", "S:2.649",
            "--conn", "S:" + unquote,
            "--token", "m9z#$dO0qe34Rxe@sMYxx",
            "--playpath", "playpath",
            "--flv", output_filename
        ]

        return subprocess.Popen(arguments)

    @staticmethod
    def get_process_stats(process_info):
        """
        Generates various info about the file being captured.

        :param dict process_info: Information about the rtmpdump process.

        :return: Statistics about the recording.
        :rtype: dict
        """
        file_size = int(os.path.getsize(process_info['filename']))
        return {
            'file_size': file_size,
            'formatted_file_size': Chaturbate.get_human_size(file_size),
            'started_at': time.strftime(
                "%H:%M", time.localtime(process_info['time'])),
            'recording_time': str(
                timedelta(seconds=int(time.time()) - process_info['time']))
        }

    def make_request(self, url):
        """
        Does a GET request and returns the HTML content.

        :param str url: The URL to open.

        :return: The HTML source of the requested URL.
        :rtype: str
        """
        request = None

        if os.path.isfile('cookie.txt'):
            with open('cookie.txt', 'r') as f:
                cookie = requests.utils.cookiejar_from_dict(json.load(f))
        else:
            cookie = {}

        while request is None:
            try:
                request = self.request.get(url, timeout=5, cookies=cookie)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.Timeout):
                request = None

            while (request is not None) and \
                    (self.is_logged(request.text) is False):
                self.log.warning("Not logged in")
                self.login()
                try:
                    request = self.request.get(url, timeout=5, cookies=cookie)
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.Timeout):
                    request = None

        return request.text

    def get_online_models(self):
        """
        Return a list with the models you follow that are online.

        This function ignores (or tries to) private shows, and offline models.

        :return: Online models name.
        :rtype: list
        """
        url = 'https://chaturbate.com/followed-cams/'
        html = self.make_request(url)
        soup = BeautifulSoup(html, "html.parser")

        models = []
        models_li = soup.find(
            'ul', {'class': 'list'}).findAll('li', recursive=False)

        for model in models_li:
            model_name = model.find('a')['href'].replace('/', '')

            # ignore offline
            if model.find('div', {'class': 'thumbnail_label_offline'}):
                continue

            # ignore private shows
            if model.find('div', {'class': 'thumbnail_label_c_private_show'}):
                continue

            models.append(model_name)

        return models

    def is_recording(self, model_name):
        """
        Checks if a model is already being recorded.

        :param str model_name: The model name to check.

        :rtype: bool
        """
        for process in self.processes:
            if process['model'] == model_name and \
                            process['type'] == 'rtmpdump':
                return True

        return False

    def process_models(self, models):
        """
        Processes a list that has the online models and starts capturing them.

        :param list models: The models.
        """
        for model in models:
            # already recording it, ignore
            if self.is_recording(model) is True:
                continue
            self.log.info("Model " + model + " is chaturbating")
            info = self.get_flv_info(model)
            # if the embed info was scrapped
            if len(info) > 0:
                # check if the show is private
                if self.is_private(info) is False:
                    self.capture(info)
                else:
                    self.log.warning("But the show is private")

    def get_flv_info(self, model_name):
        """
        Generates a list with all EmbedViewerSwf variables from the HTML.

        :param str model_name: The model name to get info.

        :return: Information from the FLV player.
        :rtype: list
        """
        url = "https://chaturbate.com/" + model_name + "/"
        html = self.make_request(url)

        flv_info = []

        embed = re.search(r"EmbedViewerSwf\(*(.+?)\);", html, re.DOTALL)
        if embed is None:
            self.log.warning('Cant find embed')
            return flv_info

        for line in embed.group(1).split("\n"):
            data = re.search(r" +[\"'](.*)?[\"'],", line)
            if data:
                flv_info.append(data.group(1))

        return flv_info

    def capture(self, flv_info):
        """
        Capture a stream.

        Starts rtmpdump and adds information to the :data:`processes` list.

        :param list flv_info: A list with all the flv info.
        """
        date_time = datetime.now()

        filename = ("Chaturbate_" + flv_info[1] +
                    date_time.strftime("_%Y-%m-%dT%H%M%S") + ".flv")
        self.log.info("Capturing %s", filename)

        filename = os.path.join(self.config['capturing_path'], filename)

        process = self.run_rtmpdump(flv_info, filename)

        self.processes.append(
            {
                'id': 'rtmp-' + flv_info[1],
                'type': 'rtmpdump',
                'model': flv_info[1],
                'filename': filename,
                'time': int(time.time()),
                'process': process,
            })

    def clean_rtmpdump(self, process_info):
        """
        Processes the flv after rtmpdump stops.

        :param dict process_info: Information about the rtmpdump process.
        """
        self.log.info("%s is no longer being captured", process_info['model'])
        if os.path.isfile(process_info['filename']):
            process_stats = self.get_process_stats(process_info)
            if process_stats['file_size'] == 0:
                self.log.warning("Capture size is 0kb, deleting.")
                os.remove(process_info['filename'])
            else:
                self.move_to_complete(process_info)
                self.log.info("Finished: %s - Started at %s | " +
                              "Size: %s | Duration: %s",
                              process_info['model'],
                              process_stats['started_at'],
                              process_stats['formatted_file_size'],
                              process_stats['recording_time'])

    def is_running(self):
        """
        Checks if a process is still running, if isn't remove it from list.

        If ffmpeg exited correctly, deletes the flv file.
        """
        remove = []

        # iterate over all "running" processes
        for process in self.processes:
            # if the process has stopped
            if process['process'].poll() is not None:
                if process['type'] == 'rtmpdump':
                    self.clean_rtmpdump(process)
                elif process['type'] == 'ffmpeg':
                    if process['process'].poll() == 0:
                        if self.config['debug'] == 'true':
                            self.log.info("Deleting %s", process['source'])
                        os.remove(process['source'])
                    else:
                        self.log.warning(
                            "ffmpeg transcode failed, not deleting flv")

                remove.append(process['id'])

        # remove all items in remove from self.processes
        temp_processes = self.processes
        for item in remove:
            temp_processes = [f for f in temp_processes if f['id'] != item]
        self.processes = temp_processes

    def kill_processes(self):
        """
        Kills all child processes, used when ^C is pressed.
        """
        for process in self.processes:
            if process['process'].poll() is not None:
                process['process'].terminate()

    def login(self):
        """
        Performs the login on the site.
        """
        self.log.info("Logging in...")
        url = 'https://chaturbate.com/'
        result = self.request.get(url)

        soup = BeautifulSoup(result.text, "html.parser")

        if soup.find('div', {'class': 'g-recaptcha'}):
            sys.exit("captcha found, bailing")
        else:
            self.log.info("No captcha found!!")

        csrf = soup.find('input', {'name': 'csrfmiddlewaretoken'}).get('value')

        url = 'https://chaturbate.com/auth/login/?next=/'

        result = self.request.post(url,
                                   data={
                                       'csrfmiddlewaretoken': csrf,
                                       'username': self.config['username'],
                                       'password': self.config['password'],
                                       'rememberme': 'on',
                                       'next': '/',
                                   },
                                   cookies=result.cookies,
                                   headers={
                                       'user-agent': self.agent,
                                       'Referer': url
                                   })

        if self.is_logged(result.text) is False:
            self.log.warning("Could not login")
            sys.exit("BYE!")
            return False
        else:
            with open('cookie.txt', 'w') as f:
                json.dump(requests.utils.dict_from_cookiejar(result.cookies), f)
            return True

    def do_cycle(self):
        """
        Does a full cycle.

        * Checks the processes.
        * Gets online models.
        * Process them.
        """
        c.is_running()
        online_models = self.get_online_models()
        self.process_models(online_models)
        self.print_recording()
        if self.config['debug'] == 'true':
            self.print_status()

    def print_status(self):
        """
        Prints number of rtmpdump and ffmpeg processes running.
        """
        capturing = 0
        processing = 0

        for process in self.processes:
            if process['type'] == 'rtmpdump':
                capturing += 1
            if process['type'] == 'ffmpeg':
                processing += 1

        self.log.info("Capturing: %d, Processing: %d",
                      capturing, processing)

    def print_recording(self):
        """
        Print statistics about cams being recorded.
        """
        for process in self.processes:
            if process['type'] == 'rtmpdump' and \
                    os.path.isfile(process['filename']):
                process_stats = self.get_process_stats(process)
                if process_stats['file_size'] > 0:
                    self.log.info("Recording: %s - Duration: %s - Size: %s",
                                  process['model'],
                                  process_stats['recording_time'],
                                  process_stats['formatted_file_size']
                                 )

    def is_private(self, rtmp_info):
        """
        Checks if a stream is private.

        Runs rtmpdump for a few seconds and checks if the file size is > 0.

        :param list rtmp_info: A list with all the rtmp info.

        :rtype: bool
        """
        result = True
        seconds = 2

        date_time = datetime.now()
        filename = ("test-" + rtmp_info[1] +
                    date_time.strftime("_%Y-%m-%dT%H%M%S") + ".flv")
        filename = os.path.join(self.config['capturing_path'], filename)
        process = self.run_rtmpdump(
            rtmp_info, filename, extra_argument="-B " + str(seconds))
        process.wait()

        if os.path.isfile(filename):
            if os.path.getsize(filename) > 0:
                result = False
            os.remove(filename)

        return result

    def move_to_complete(self, process):
        """
        Moves the recorded file to the completed path.

        If ffmpeg postprocessing is enabled, its called after the move.

        :param dict process: A dict with information about a rtmpdump process.
        """
        source = process['filename']
        flv = source.replace(
            self.config['capturing_path'] + os.sep,
            self.config['completed_path'] + os.sep)
        os.rename(source, flv)

        if self.config['ffmpeg'] == "true":
            mp4 = flv.replace(".flv", ".mp4")
            self.run_ffmpeg(process['model'], flv, mp4)

    def run_ffmpeg(self, model_name, source_fn, destination_fn):
        """
        Executes ffmpeg to postprocess recording.

        :param str model_name: Model name.
        :param str source_fn: Source file, normally the flv file.
        :param str destination_fn: Destination file, normally a mp4.
        """
        arguments = [
            ['ffmpeg', '-nostats', '-loglevel', '0', '-y', '-threads', '1', '-i', source_fn],
            self.config['ffmpeg-flags'].split(),
            [destination_fn],
        ]

        arguments = [item for sublist in arguments for item in sublist]

        if self.config['debug'] == 'true':
            self.log.info("Running: %s", ' '.join(arguments))

        process = subprocess.Popen(arguments, stdout=DEVNULL,
                                   stderr=DEVNULL)

        self.processes.append(
            {
                'id': 'ffmpeg-' + model_name,
                'type': 'ffmpeg',
                'model': model_name,
                'source': source_fn,
                'destination': destination_fn,
                'process': process,
            })


if __name__ == "__main__":
    c = Chaturbate()
    while True:
        try:
            c.do_cycle()
            time.sleep(60)
        except KeyboardInterrupt:
            c.kill_processes()
            sys.exit()
