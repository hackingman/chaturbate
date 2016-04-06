#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
This example module automatically records shows from your followed models
using rtmpdump.

The requirements are:
    RTMPDump-ksv - https://github.com/BurntSushi/rtmpdump-ksv
    BeautifulSoup - https://www.crummy.com/software/BeautifulSoup/
    requests - http://docs.python-requests.org/en/master/
    hurry.filesize - https://pypi.python.org/pypi/hurry.filesize/
"""

import subprocess
import re
import urllib
import time
import ConfigParser
import os
import sys
import signal
from datetime import datetime, timedelta
import logging
import requests
from hurry.filesize import size
from bs4 import BeautifulSoup
from pushbullet import Pushbullet


class Chaturbate(object):
    """
    All-in-one class to record chaturbate streams
    """
    username = ''
    password = ''
    req = None
    processes = []
    logger = None
    push_bullet = None

    def __init__(self):
        """
        Instantiates the class.
        Reads username and password from config.ini
        """

        # Configure logging
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

        # Read configuration
        config_parser = ConfigParser.ConfigParser()
        config_parser.read("config.ini")

        # Try to connect to pushbullet
        try:
            self.push_bullet = Pushbullet(config_parser.get('User', 'pushbullet'))
        except pushbullet.InvalidKeyError:
            self.push_bullet = None

        # Create a requests object that has sessions
        self.req = requests.Session()

        self.username = config_parser.get('User', 'username')
        self.password = config_parser.get('User', 'password')

    @staticmethod
    def is_logged(html):
        """
        Checks if youre currently logged in
        """
        soup = BeautifulSoup(html, "html.parser")

        if soup.find('div', {'id': 'user_information'}) is None:
            return False
        return True

    @staticmethod
    def run_rtmpdump(info, output):
        """
        Starts an rtmpdump with information given to the ouput file
        """
        args = [
            "rtmpdump",
            "--quiet",
            "--live",
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

    def make_request(self, url):
        """
        Does a GET request, and login if required
        """
        result = self.req.get(url)

        while self.is_logged(result.text) is False:
            self.logger.warning("Not logged in")
            self.login()
            result = self.req.get(url)

        return result.text

    def get_online_models(self):
        """
        Return a list of your online followed models
        """

        url = 'https://chaturbate.com/followed-cams/'
        html = self.make_request(url)
        soup = BeautifulSoup(html, "html.parser")

        models = []
        models_li = soup.find('ul', {'class': 'list'}).findAll('li', recursive=False)

        for model in models_li:
            name = model.find('a')['href'].replace('/', '')

            # private show
            if model.find('div', {'class': 'thumbnail_label_c_private_show'}):
                continue

            # offline
            status = model.find('div', {'class': 'thumbnail_label'}).text
            if status == "OFFLINE":
                continue

            models.append(name)

        return models

    def is_recording(self, model):
        """
        Checks if a model is already being recorded
        """
        return model in [proc['model'] for proc in self.processes]

    def process_models(self, models):
        """
        Processes a list that has the online models
        and starts capturing them
        """
        for model in models:
            # already recording it, ignore
            if self.is_recording(model) is True:
                continue
            self.logger.info("Model " + model + " is chaturbating")
            info = self.get_model_info(model)
            if len(info) > 0:
                if self.is_private(info) is False:
                    self.capture(info)
                else:
                    self.logger.warning("But the show is private")

    def get_model_info(self, name):
        """
        Returns a list with all EmbedViewerSwf variables from the model
        """
        url = "https://chaturbate.com/" + name + "/"
        html = self.make_request(url)

        info = []

        embed = re.search(r"EmbedViewerSwf\(*(.+?)\);", html, re.DOTALL)
        if embed is None:
            self.logger.warning('Cant find embed')
            return info

        for line in embed.group(1).split("\n"):
            data = re.search(""" +["'](.*)?["'],""", line)
            if data:
                info.append(data.group(1))

        return info

    def capture(self, info):
        """
        Starts capturing the stream with rtmpdump
        """
        date_time = datetime.now()
        filename = "Chaturbate_" + info[1] + date_time.strftime("_%Y-%m-%dT%H%M%S") + ".flv"

        message = "Capturing " + filename
        if self.push_bullet is not None:
            self.push_bullet.push_note("Chaturbate", message)
        self.logger.info(message)

        proc = self.run_rtmpdump(info, filename)

        self.processes.append(
            {
                'model': info[1],
                'filename': filename,
                'time': int(time.time()),
                'proc': proc,
            })

    def check_running(self):
        """
        Checks if the rtmpdump processes are still running
        """
        remove = []

        for proc in self.processes:
            if proc['proc'].poll() is not None:
                self.logger.info(proc['model'] + " is no longer being captured")
                if os.path.isfile(proc['filename']):
                    file_size = os.path.getsize(proc['filename'])
                    if file_size > 0:
                        self.logger.warning("Capture size is 0kb, deleting. Show probably is private")
                        os.remove(proc['filename'])
                    else:
                        if self.push_bullet is not None:
                            started_at = time.strftime("%D %H:%M", time.localtime(proc['time']))
                            recording_time = str(timedelta(seconds=int(time.time()) - proc['time']))
                            formatted_file_size = size(file_size)
                            self.push_bullet.push_note("Chaturbate", "Finished: " + proc['model'] + " - " +
                                                       "Started at " + started_at + " | " +
                                                       "Size: " + formatted_file_size + " | " +
                                                       "Duration: " + recording_time)

                remove.append(proc['model'])

        procs = self.processes
        for item in remove:
            procs = [f for f in procs if f['model'] != item]
        self.processes = procs

    def kill_processes(self):
        """
        Kills all child processes, used when ^C
        """
        for proc in self.processes:
            os.kill(proc['proc'].pid, signal.SIGTERM)

    def login(self):
        """
        Performs the login on the site
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
        """
        Do a full cycle
        """
        c.check_running()
        online_models = self.get_online_models()
        if len(online_models) > 0:
            self.process_models(online_models)
        self.print_recording()

    def print_recording(self):
        """
        Print statistics about cams being recorded
        """
        for proc in self.processes:
            if os.path.isfile(proc['filename']):
                file_size = os.path.getsize(proc['filename'])
                if file_size > 0:
                    started_at = time.strftime("%D %H:%M", time.localtime(proc['time']))
                    recording_time = str(timedelta(seconds=int(time.time()) - proc['time']))
                    formatted_file_size = size(file_size)
                    self.logger.info("Recording: " + proc['model'] + " - " +
                                     "Started at " + started_at + " | " +
                                     "Size: " + formatted_file_size + " | " +
                                     "Duration: " + recording_time)

    def is_private(self, info):
        """
        Tries to check if a stream is private.
        Runs rtmpdump for 10 seconds and checks if it recorded anything
        """
        result = True

        file_name = "test.flv"
        proc = self.run_rtmpdump(info, file_name)
        time.sleep(10)
        if os.path.isfile(file_name):
            if os.path.getsize(file_name) > 0:
                result = False

        proc.terminate()
        os.remove(file_name)

        return result

if __name__ == "__main__":
    c = Chaturbate()
    while True:
        try:
            c.do_cycle()
            time.sleep(60)
        except KeyboardInterrupt:
            c.kill_processes()
            sys.exit()
