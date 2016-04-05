#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
This example module automatically records shows from your followed models
using rtmpdump.

The requirements are:
    RTMPDump-ksv - https://github.com/BurntSushi/rtmpdump-ksv
    BeautifulSoup - https://www.crummy.com/software/BeautifulSoup/
    requests - http://docs.python-requests.org/en/master/
"""

import subprocess
import re
import urllib
import time
import ConfigParser
import os
import sys
import signal
from datetime import datetime
import requests
from bs4 import BeautifulSoup


class Chaturbate(object):
    """
    All-in-one class to record chaturbate streams
    """
    username = ''
    password = ''
    req = None
    processes = []

    def __init__(self):
        """
        Instantiates the class.
        Reads username and password from config.ini
        """
        config_parser = ConfigParser.ConfigParser()
        config_parser.read("config.ini")
        self.username = config_parser.get('User', 'username')
        self.password = config_parser.get('User', 'password')
        self.req = requests.Session()

    @staticmethod
    def debug(message):
        """
        Prints a log message
        """
        date_time = datetime.now()
        print "[" + date_time.strftime("%Y-%m-%dT%H%M%S") + "] " + message

    @staticmethod
    def is_logged(html):
        """
        Checks if youre currently logged in
        """
        soup = BeautifulSoup(html, "html.parser")

        if soup.find('div', {'id': 'user_information'}) is None:
            return False
        return True

    def make_request(self, url):
        """
        Does a GET request, and login if required
        """
        result = self.req.get(url)

        while self.is_logged(result.text) is False:
            self.debug("[ERR]: Not logged in")
            self.login()
            result = self.req.get(url)

        return result.text

    def get_online_models(self):
        """
        Return a list of your online followed models
        """
        self.debug("Getting models list...")

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

        if len(models) == 0:
            self.debug("No online models found")

        return models

    def is_recording(self, model):
        """
        Checks if a model is already being recorded
        """
        # TODO: PRETIFY
        for proc in self.processes:
            if proc['model'] == model:
                return True
        return False

    def process_models(self, models):
        """
        Processes a list that has the online models
        and starts capturing them
        """
        for model in models:
            self.debug("Model " + model + " is chaturbating")
            if self.is_recording(model) is True:
                self.debug("Already recording")
                continue
            info = self.get_model_info(model)
            if len(info) > 0:
                self.capture(info)

    def get_model_info(self, name):
        """
        Returns a list with all EmbedViewerSwf variables from the model
        """
        self.debug("Getting " + name + " info...")
        url = "https://chaturbate.com/" + name + "/"

        html = self.make_request(url)

        info = []

        embed = re.search(r"EmbedViewerSwf\(*(.+?)\);", html, re.DOTALL)
        if embed is None:
            self.debug('Cant find embed')
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

        self.debug("Capturing " + filename)

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
            "--flv", filename
        ]

        proc = subprocess.Popen(args)
        self.processes.append({'model': info[1], 'proc': proc, 'filename': filename})

    def check_running(self):
        """
        Checks if the rtmpdump processes are still running
        """
        remove = []

        for proc in self.processes:
            if proc['proc'].poll() is not None:
                self.debug(proc['model'] + " is no longer being captured")
                if os.path.getsize(proc['filename']) == 0:
                    self.debug("Capture size is 0, deleting")
                    os.remove(proc['filename'])
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
        self.debug("Logging in...")
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
            self.debug("[ERR]: Could not login")
            return False
        else:
            self.debug("[OK]: Logged in")
            return True

if __name__ == "__main__":
    c = Chaturbate()
    while True:
        try:
            c.process_models(c.get_online_models())
            time.sleep(60)
            c.check_running()
        except KeyboardInterrupt:
            c.kill_processes()
            sys.exit()
