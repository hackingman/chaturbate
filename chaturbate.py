#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
import requests, subprocess, re, urllib, time, ConfigParser
import os, sys, signal
from datetime import datetime

class Chaturbate:
    username = ''
    password = ''
    req = None
    processes = []

    @staticmethod
    def debug(message):
        dt = datetime.now()
        print "[" + dt.strftime("%Y-%m-%dT%H%M%S") + "] " + message

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.req = requests.Session()

    def getModels(self):
        self.debug("Getting models list...")

        url = 'https://chaturbate.com/followed-cams/'
        r = self.req.get(url)

        while (self.isLogged(html=r.text) == False):
            self.debug("[ERR]: Not logged in")
            self.login()
            r = self.req.get(url)

        s = BeautifulSoup(r.text, "html.parser")

        models = []
        modelsLi = s.find('ul', {'class': 'list'}).findAll('li', recursive=False)
        for model in modelsLi:
            m = {}
            m['name'] = model.find('a')['href'].replace('/','')

            if (model.find('div', {'class': 'thumbnail_label_c_private_show'})):
                self.debug(m['name'] + " is in a private show, ignoring...")
                continue

            m['status'] = model.find('div', {'class': 'thumbnail_label'}).text
            models.append(m)

        if (len(models) == 0):
            self.debug("No Online models found")

        return models

    def isRecording(self, model):
        for proc in self.processes:
            if proc['model'] == model:
                return True
        return False


    def processModels(self, models):
        for model in models:
            if (model['status'] != 'OFFLINE'):
                self.debug("Model " + model['name'] + " is chaturbating")
                if (self.isRecording(model['name']) == True):
                    self.debug("Already recording")
                    continue
                info = self.getModelInfo(model['name'])
                if (len(info)>0):
                    self.capture(info)

    def getModelInfo(self, name):
        self.debug("Getting " + name + " info...")
        url = "https://chaturbate.com/" + name + "/"
        r = self.req.get(url)

        while (self.isLogged(html=r.text) == False):
            self.debug("[ERR]: Not logged in")
            self.login()
            r = self.req.get(url)

        info = []

        embed = re.search(r"EmbedViewerSwf\(*(.+?)\);", r.text, re.DOTALL)
        if embed == None:
            self.debug('Cant find embed')
            return info
            #raise Exception('Cant find Model Info')

        for line in embed.group(1).split("\n"):
            data = re.search(""" +["'](.*)?["'],""", line)
            if data:
                info.append(data.group(1))

        return info

    def capture(self, info):
        dt = datetime.now()
        filename = "Chaturbate_" +  info[1] + dt.strftime("_%Y-%m-%dT%H%M%S") +".flv"

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

    def checkRunning(self):
        remove = []

        for proc in self.processes:
            if (proc['proc'].poll() != None):
                self.debug(proc['model'] + " is no longer being captured")
                if (os.path.getsize(proc['filename']) == 0):
                    self.debug("Capture size is 0, deleting")
                    os.remove(proc['filename'])
                remove.append(proc['model'])

        procs = self.processes
        for item in remove:
            procs = [f for f in procs if f['model'] != item]
        self.processes = procs

    def killProcesses(self):
        for proc in self.processes:
            os.kill(proc['proc'].pid, signal.SIGTERM)

    def isLogged(self, url=None, html=None):
        if (url != None):
            r = self.req.get(url)
            text = r.text
        if (html != None):
            text = html

        s = BeautifulSoup(text, "html.parser")

        if (s.find('div', {'id': 'user_information'}) == None):
            return False
        return True

    def login(self):
        self.debug("Logging in...")
        url = 'https://chaturbate.com/auth/login/'
        r = self.req.get(url)

        s = BeautifulSoup(r.text, "html.parser")
        csrf = s.find('input', {'name': 'csrfmiddlewaretoken'}).get('value')

        r = self.req.post(url,
            data = {'username': self.username, 'password': self.password, 'csrfmiddlewaretoken': csrf},
            cookies = r.cookies,
            headers = {'Referer': url})

        if (self.isLogged(html=r.text) == False):
            self.debug("[ERR]: Could not login")
            return False
        else:
            self.debug("[OK]: Logged in")
            return True

if __name__ == "__main__":
    Config = ConfigParser.ConfigParser()
    Config.read("config.ini")
    c = Chaturbate(Config.get('User', 'username'), Config.get('User', 'password'))
    while True:
        try:
            c.processModels(c.getModels())
            time.sleep(60)
            c.checkRunning()
        except KeyboardInterrupt:
            c.killProcesses()
            sys.exit()
