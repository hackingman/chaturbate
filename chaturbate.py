#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
This module automatically records shows from your followed models
using rtmpdump.

The requirements are:
 * RTMPDump-ksv - https://github.com/BurntSushi/rtmpdump-ksv
 * BeautifulSoup - https://www.crummy.com/software/BeautifulSoup/
 * requests - http://docs.python-requests.org/en/master/
 * hurry.filesize - https://pypi.python.org/pypi/hurry.filesize/
 * pushbullet.py - https://github.com/randomchars/pushbullet.py (optional)
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
from hurry.filesize import size
from bs4 import BeautifulSoup


class Chaturbate(object):
    """
    All-in-one class to record Chaturbate streams.
    """
    username = ''
    """The username read from the config."""
    password = ''
    """The password read from the config."""
    req = None
    """The requests object with sessions."""
    processes = []
    """A list with all the started/running processes."""
    logger = None
    """An instance of the python logger."""
    push_bullet = None
    """An instance of a pushbullet object."""
    config_parser = None

    def __init__(self):
        """
        Configures logging, reads configuration and tries to enable pushbullet
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

        # is pushbullet is enabled on the config
        if self.config_parser.get('PushBullet', 'enable') == 'true':
            # try to import it and connect
            try:
                import pushbullet
                self.push_bullet = pushbullet.Pushbullet(
                    self.config_parser.get('PushBullet', 'access_token'))
            except (ImportError, pushbullet.InvalidKeyError):
                self.push_bullet = None

        # create a requests object that has sessions
        self.req = requests.Session()

        self.username = self.config_parser.get('User', 'username')
        self.password = self.config_parser.get('User', 'password')

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
    def run_rtmpdump(info, output, extra_arg=""):
        """Runs rtmpdump with the provided parameters.

        :param info list: A list with all the rtmp info, generated in :func:`get_model_info`.
        :param output str: Filename where to output the stream.

        :return: A Popen object (process).
        :rtype: Popen
        """
        args = [
            "rtmpdump",
            "--quiet",
            "--live",
            extra_arg,
            "--rtmp", "rtmp://" + info[2] + "/live-edge",
            "--pageUrl", "http://chaturbate.com/" + info[1],
            "--conn", "S:" + info[8],
            "--conn", "S:" + info[1],
            "--conn", "S:2.645",
            "--conn", "S:" + urllib.unquote(info[15]),
            "--token", "m9z#$dO0qe34Rxe@sMYxx",
            "--playpath", "playpath",
            "--flv", output
        ]

        return subprocess.Popen(args)

    @staticmethod
    def get_proc_stats(proc):
        """Generates a dict with various info about the file being captured.

        :param proc dict: A dict with information about a rtmpdump process, generated in :func:`capture`.

        :return: A dict with statistics about the recording.
        :rtype: dict
        """
        file_size = os.path.getsize(proc['filename'])
        return {
            'file_size': file_size,
            'formatted_file_size': size(file_size),
            'started_at': time.strftime(
                "%H:%M", time.localtime(proc['time'])),
            'recording_time': str(
                timedelta(seconds=int(time.time()) - proc['time']))
            }

    def make_request(self, url):
        """Does a GET request and returns the HTML content.

        :param url str: The URL to open.

        :return: The HTML source of the requested URL.
        :rtype: str
        """
        try:
            result = self.req.get(url)
        except requests.exceptions.ConnectionError:
            result = None

        while (result is None) or (self.is_logged(result.text) is False):
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
            status = model.find('div', {'class': 'thumbnail_label'}).text
            if status == "OFFLINE":
                continue

            models.append(name)

        return models

    def is_recording(self, model):
        """Checks if a model is already being recorded.

        Checks if the parameter is already in the :data:`processes` list.

        :param model str: The model name to check.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        return model in [proc['model'] for proc in self.processes]

    def process_models(self, models):
        """Processes a list that has the online models and starts capturing them.

        :param models list: The models list generated in :func:`get_online_models`.
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

    def get_model_info(self, name):
        """Generates a list with all EmbedViewerSwf variables from the HTML.

        :param model str: The model name to get info.

        :return: A list with all informations for the FLV player.
        :rtype: list
        """
        url = "https://chaturbate.com/" + name + "/"
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

    def capture(self, info):
        """Capture a stream.

        After running the rtmpdump process this adds some information about it to the :data:`processes` list.

        :param info list: A list with all the rtmp info, generated in :func:`get_model_info`.
        """
        directory = self.config_parser.get('Directories', 'capturing')

        if os.path.isdir(directory) is False:
            os.mkdir(directory)

        date_time = datetime.now()

        filename = ("Chaturbate_" + info[1] +
                    date_time.strftime("_%Y-%m-%dT%H%M%S") + ".flv")

        message = "Capturing " + filename
        self.logger.info(message)
        if self.push_bullet is not None:
            self.push_bullet.push_note("Chaturbate", message)

        filename = os.path.join(directory, filename)

        proc = self.run_rtmpdump(info, filename)

        self.processes.append(
            {
                'id': 'rtmp-' + info[1],
                'type': 'rtmpdump',
                'model': info[1],
                'filename': filename,
                'time': int(time.time()),
                'proc': proc,
            })

    def check_running(self):
        """Checks if the processes are still running.

        This function checks if the :data:`processes` are still running.
        If they arent, remove them from the list.
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
                        proc_stats = self.get_proc_stats(proc)
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
                            if self.push_bullet is not None:
                                self.push_bullet.push_note("Chaturbate", message)
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
        c.check_running()
        online_models = self.get_online_models()
        if len(online_models) > 0:
            self.process_models(online_models)
        self.print_recording()

    def print_recording(self):
        """Print statistics about cams being recorded.
        """
        for proc in self.processes:
            if proc['type'] == 'rtmpdump' and os.path.isfile(proc['filename']):
                proc_stats = self.get_proc_stats(proc)
                if proc_stats['file_size'] > 0:
                    message = ("Recording: " +
                               proc['model'] + " - " +
                               "Duration: " +
                               proc_stats['recording_time'] + " - " +
                               "Size: " +
                               proc_stats['formatted_file_size'])
                    self.logger.info(message)

    def is_private(self, info):
        """Checks if a stream is private.

        Runs rtmpdump for 10 seconds and checks if the file size is > 0.

        :param list info: A list with all the rtmp info, generated in :func:`get_model_info`.

        :return: True if private, False otherwise.
        :rtype: bool
        """
        result = True
        seconds = 5

        file_name = "test.flv"
        proc = self.run_rtmpdump(info, file_name, extra_arg="-B " + str(seconds))
        proc.wait()

        if os.path.isfile(file_name):
            if os.path.getsize(file_name) > 0:
                result = False
            os.remove(file_name)

        return result

    def move_to_complete(self, proc):
        directory = self.config_parser.get('Directories', 'complete')

        if os.path.isdir(directory) is False:
            os.mkdir(directory)

        source = proc['filename']
        flv = source.replace(self.config_parser.get('Directories', 'capturing') + os.sep,
                             self.config_parser.get('Directories', 'complete') + os.sep)
        os.rename(source, flv)
        mp4 = flv.replace(".flv", ".mp4")

        if self.config_parser.get('FFmpeg', 'enable') == "true":
            self.run_ffmpeg(proc['model'], flv, mp4)

    def run_ffmpeg(self, model, source, destination):
        args = [
                ['ffmpeg', '-i', source],
                self.config_parser.get('FFmpeg', 'options').split(),
                [destination]
                ]

 
        args = [item for sublist in args for item in sublist]

        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = proc.communicate()

        self.processes.append(
            {
                'id': 'ffmpeg-' + model,
                'type': 'ffmpeg',
                'model': model,
                'source': source,
                'destination': destination,
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
