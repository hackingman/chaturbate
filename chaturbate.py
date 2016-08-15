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

import subprocess
import re
import urllib
import time
import ConfigParser
import os
import sys
from datetime import datetime, timedelta
import logging
import requests
from bs4 import BeautifulSoup


class Chaturbate(object):
    """
    All-in-one class to record Chaturbate streams.
    """
    username = ''
    """The username read from the config."""
    password = ''
    """The password read from the config."""
    processes = []
    """A list with all the processes."""
    req = None
    """An instance of the requests class."""
    logger = None
    """An instance of the Python logger."""
    config_parser = None
    """An instance of the ConfigParser."""

    def __init__(self):
        """
        Configures logging, reads configuration
        """

        # configure logging
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        self.logger = logging.getLogger("chaturbate")
        self.logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                      "%Y-%m-%d %H:%M:%S")
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # read configuration
        self.config_parser = ConfigParser.ConfigParser()
        self.config_parser.read("config.ini")

        # create a requests object that has sessions
        self.req = requests.Session()

        self.username = self.config_parser.get('User', 'username')
        self.password = self.config_parser.get('User', 'password')

    @staticmethod
    def get_human_size(bytes):
        """Returns file size in a human readable format.

        :param int bytes: File size in bytes
        :return: Pretty file size
        :rtype: str
        """
        suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        if bytes == 0:
            return '0 B'
        i = 0
        while bytes >= 1024 and i < len(suffixes)-1:
            bytes /= 1024.
            i += 1
        f = ('%.2f' % bytes).rstrip('0').rstrip('.')
        return '%s %s' % (f, suffixes[i])

    @staticmethod
    def is_logged(html):
        """Checks if you're currently logged in.

        Searches the HTML with BeautifulSoup to see if there is a
        <div id='user_information'> in it.
        If its found then we are logged in.

        :param str html: The HTML source to check.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        soup = BeautifulSoup(html, "html.parser")

        if soup.find('div', {'id': 'user_information'}) is None:
            return False
        return True

    @staticmethod
    def run_rtmpdump(rtmp_info, output_filename, extra_argument=""):
        """Runs rtmpdump with the provided parameters.

        :param list rtmp_info: A list with all the rtmp info, generated in :func:`get_model_info`.
        :param str output_filename: Filename where to output the stream.
        :param str extra_argument: Extra argument to pass to rtmpdump.

        :return: A Popen object (process).
        :rtype: Popen
        """
        args = [
            "rtmpdump",
            "--quiet",
            "--live",
            extra_argument,
            "--rtmp", "rtmp://" + rtmp_info[2] + "/live-edge",
            "--pageUrl", "http://chaturbate.com/" + rtmp_info[1],
            "--conn", "S:" + rtmp_info[8],
            "--conn", "S:" + rtmp_info[1],
            "--conn", "S:2.645",
            "--conn", "S:" + urllib.unquote(rtmp_info[15]),
            "--token", "m9z#$dO0qe34Rxe@sMYxx",
            "--playpath", "playpath",
            "--flv", output_filename
        ]

        return subprocess.Popen(args)

    @staticmethod
    def get_process_stats(process):
        """Generates a dict with various info about the file being captured.

        :param dict process: A dict with information about a rtmpdump process, generated in :func:`capture`.

        :return: A dict with statistics about the recording.
        :rtype: dict
        """
        file_size = int(os.path.getsize(process['filename']))
        return {
            'file_size': file_size,
            'formatted_file_size': Chaturbate.get_human_size(file_size),
            'started_at': time.strftime(
                "%H:%M", time.localtime(process['time'])),
            'recording_time': str(
                timedelta(seconds=int(time.time()) - process['time']))
            }

    def make_request(self, url):
        """Does a GET request and returns the HTML content.

        :param str url: The URL to open.

        :return: The HTML source of the requested URL.
        :rtype: str
        """
        result = None

        while result is None:
            try:
                result = self.req.get(url)
            except requests.exceptions.ConnectionError:
                result = None

            while (result is not None) and (self.is_logged(result.text) is False):
                self.logger.warning("Not logged in")
                self.login()
                try:
                    result = self.req.get(url)
                except requests.exceptions.ConnectionError:
                    result = None

        return result.text

    def get_online_models(self):
        """Return a list with the models you follow that are online.

        This function ignores (or tries to) private shows, and offline models.

        :return: A list with the online models name.
        :rtype: list
        """
        url = 'https://chaturbate.com/followed-cams/'
        html = self.make_request(url)
        soup = BeautifulSoup(html, "html.parser")

        models = []
        models_li = soup.find(
            'ul', {'class': 'list'}).findAll('li', recursive=False)

        for model in models_li:
            name = model.find('a')['href'].replace('/', '')

            # it seems that when <div class='thumbnail_label_c_private_show'>
            # exists on the model <li> then the show is private
            if model.find('div', {'class': 'thumbnail_label_c_private_show'}):
                continue

            # if the status message is "OFFLINE", then who am i to doubt it
            if model.find('div', {'class': 'thumbnail_label_offline'}):
                continue

            models.append(name)

        return models

    def is_recording(self, model_name):
        """Checks if a model is already being recorded.

        Checks if the parameter is already in the :data:`processes` list.

        :param str model_name: The model name to check.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        for process in self.processes:
            if process['model'] == model_name and process['type'] == 'rtmpdump':
                return True

        return False

    def process_models(self, models):
        """Processes a list that has the online models and starts capturing them.

        :param list models: The models list generated in :func:`get_online_models`.
        """
        for model in models:
            # already recording it, ignore
            if self.is_recording(model) is True:
                continue
            self.logger.info("Model " + model + " is chaturbating")
            info = self.get_model_info(model)
            # if the embed info was scrapped
            if len(info) > 0:
                # check if the show is private
                if self.is_private(info) is False:
                    self.capture(info)
                else:
                    self.logger.warning("But the show is private")

    def get_model_info(self, model_name):
        """Generates a list with all EmbedViewerSwf variables from the HTML.

        :param str model_name: The model name to get info.

        :return: A list with all information from the FLV player.
        :rtype: list
        """
        url = "https://chaturbate.com/" + model_name + "/"
        html = self.make_request(url)

        info = []

        embed = re.search(r"EmbedViewerSwf\(*(.+?)\);", html, re.DOTALL)
        if embed is None:
            self.logger.warning('Cant find embed')
            return info

        for line in embed.group(1).split("\n"):
            data = re.search(r" +[\"'](.*)?[\"'],", line)
            if data:
                info.append(data.group(1))

        return info

    def capture(self, rtmp_info):
        """Capture a stream.

        Starts rtmpdump and adds information about it to the :data:`processes` list.

        :param list rtmp_info : A list with all the rtmp info, generated in :func:`get_model_info`.
        """
        directory = self.config_parser.get('Directories', 'capturing')

        if os.path.isdir(directory) is False:
            os.mkdir(directory)

        date_time = datetime.now()

        filename = ("Chaturbate_" + rtmp_info[1] +
                    date_time.strftime("_%Y-%m-%dT%H%M%S") + ".flv")

        message = "Capturing " + filename
        self.logger.info(message)

        filename = os.path.join(directory, filename)

        proc = self.run_rtmpdump(rtmp_info, filename)

        self.processes.append(
            {
                'id': 'rtmp-' + rtmp_info[1],
                'type': 'rtmpdump',
                'model': rtmp_info[1],
                'filename': filename,
                'time': int(time.time()),
                'proc': proc,
            })

    def is_running(self):
        """Processes the :data:`processes` list.

        Checks if the rtmpdump is still running, if isn't remove it from list.

        Also checks if ffmpeg exited correctly and deletes flv file.
        """
        remove = []

        # iterate over all "running" processes
        for proc in self.processes:
            # if the process has stopped
            if proc['proc'].poll() is not None:
                if proc['type'] == 'rtmpdump':
                    self.logger.info(
                        proc['model'] + " is no longer being captured")
                    if os.path.isfile(proc['filename']):
                        proc_stats = self.get_process_stats(proc)
                        if proc_stats['file_size'] == 0:
                            self.logger.warning("Capture size is 0kb, deleting.")
                            os.remove(proc['filename'])
                        else:
                            self.move_to_complete(proc)
                            message = ("Finished:" +
                                       proc['model'] + " - " +
                                       "Started at " +
                                       proc_stats['started_at'] + " | " +
                                       "Size:" +
                                       proc_stats['formatted_file_size'] + " | " +
                                       "Duration:" +
                                       proc_stats['recording_time'])
                            self.logger.info(message)
                elif proc['type'] == 'ffmpeg':
                    if proc['proc'].poll() == 0:
                        os.remove(proc['source'])
                    else:
                        self.logger.warning("Something went wrong with ffmpeg, not deleting")

                remove.append(proc['id'])

        # remove all items in remove from self.processes
        procs = self.processes
        for item in remove:
            procs = [f for f in procs if f['id'] != item]
        self.processes = procs

    def kill_processes(self):
        """Kills all child processes, used when ^C is pressed.
        """
        for proc in self.processes:
            if proc['proc'].poll() is not None:
                proc['proc'].terminate()

    def login(self):
        """Performs the login on the site.
        """
        self.logger.info("Logging in...")
        url = 'https://chaturbate.com/auth/login/'
        result = self.req.get(url)

        soup = BeautifulSoup(result.text, "html.parser")
        csrf = soup.find('input', {'name': 'csrfmiddlewaretoken'}).get('value')

        result = self.req.post(url,
                               data={
                                   'username': self.username,
                                   'password': self.password,
                                   'csrfmiddlewaretoken': csrf
                               },
                               cookies=result.cookies,
                               headers={'Referer': url})

        if self.is_logged(result.text) is False:
            self.logger.warning("Could not login")
            return False
        else:
            return True

    def do_cycle(self):
        """Does a full cycle.

        * Checks the processes.
        * Gets online models.
        * Process them.
        """
        c.is_running()
        online_models = self.get_online_models()
        if len(online_models) > 0:
            self.process_models(online_models)
        self.print_recording()

    def print_recording(self):
        """Print statistics about cams being recorded.
        """
        for proc in self.processes:
            if proc['type'] == 'rtmpdump' and os.path.isfile(proc['filename']):
                proc_stats = self.get_process_stats(proc)
                if proc_stats['file_size'] > 0:
                    message = ("Recording: " +
                               proc['model'] + " - " +
                               "Duration: " +
                               proc_stats['recording_time'] + " - " +
                               "Size: " +
                               proc_stats['formatted_file_size'])
                    self.logger.info(message)

    def is_private(self, rtmp_info):
        """Checks if a stream is private.

        Runs rtmpdump for 5 seconds and checks if the file size is > 0.

        :param list rtmp_info: A list with all the rtmp info, generated in :func:`get_model_info`.

        :return: True if private, False otherwise.
        :rtype: bool
        """
        result = True
        seconds = 5

        file_name = "test.flv"
        proc = self.run_rtmpdump(rtmp_info, file_name, extra_argument="-B " + str(seconds))
        proc.wait()

        if os.path.isfile(file_name):
            if os.path.getsize(file_name) > 0:
                result = False
            os.remove(file_name)

        return result

    def move_to_complete(self, process):
        """Moves the recorded file to the completed path.

        If ffmpeg postprocessing is enabled, its called after the move.

        :param dict process: A dict with information about a rtmpdump process, generated in :func:`capture`.
        """
        directory = self.config_parser.get('Directories', 'complete')

        if os.path.isdir(directory) is False:
            os.mkdir(directory)

        source = process['filename']
        flv = source.replace(self.config_parser.get('Directories', 'capturing') + os.sep,
                             self.config_parser.get('Directories', 'complete') + os.sep)
        os.rename(source, flv)

        if self.config_parser.get('FFmpeg', 'enable') == "true":
            mp4 = flv.replace(".flv", ".mp4")
            self.run_ffmpeg(process['model'], flv, mp4)

    def run_ffmpeg(self, model_name, source_fn, destination_fn):
        """Executes ffmpeg to postprocess recording.

        :param str model_name: Model name.
        :param str source_fn: Source file, normally the flv file.
        :param str destination_fn: Destination file, normally a mp4.
        """
        args = [
            ["nice", "-n", "19"],
            ['ffmpeg', '-i', source_fn],
            self.config_parser.get('FFmpeg', 'options').split(),
            [destination_fn]
            ]

        args = [item for sublist in args for item in sublist]

        DEVNULL = open(os.devnull, 'wb')
        proc = subprocess.Popen(args, stdout=DEVNULL, stderr=subprocess.STDOUT)

        self.processes.append(
            {
                'id': 'ffmpeg-' + model_name,
                'type': 'ffmpeg',
                'model': model_name,
                'source': source_fn,
                'destination': destination_fn,
                'proc': proc,
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
