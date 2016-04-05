[![Codacy Badge](https://api.codacy.com/project/badge/grade/33a18d5c205d436487e245f4c1a44650)](https://www.codacy.com/app/falsovsky/chaturbate)

# Chaturbate

Chaturbate (great original name) is a python script to automate the recording of cam shows in Chaturbate.

The cams to record are the models that you **followed** on the site.

### Configuration

Copy **config.ini.dist** to **config.ini** and edit it. Set your username and password.

### Requirements

* [rtmpdump-ksv](https://github.com/BurntSushi/rtmpdump) - To record the rtmp streams.

You'll have to install this rtmpdump version from source.

* [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) - To parse the HTML.
* [hurry.filesize](https://pypi.python.org/pypi/hurry.filesize/) - To get pretty formatted file sizes.
* [requests](http://docs.python-requests.org/en/master/) - To make requests and keep the session.

These three can be installed with pip (see below).

### Installation

```sh
$ git clone https://github.com/falsovsky/chaturbate.git chaturbate
$ cd chaturbate
$ sudo pip install -r requirements.txt
...
$ python chaturbate.py
```

### Development

Want to contribute? Great! Submit a Pull Request.

### Todos

- Find a better way to detect private shows.

License
----

BSD
