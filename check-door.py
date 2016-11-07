#!/usr/bin/python2

import datetime
import dateutil.parser    # pip install python-dateutil
import logging
import logging.handlers
import json
import os
import sys
import time
import urllib2

appDir = os.path.dirname(os.path.realpath(sys.argv[0]))
now = datetime.datetime.now()

# Logging
appDir = os.path.dirname(os.path.realpath(sys.argv[0]))
logFormat = logging.Formatter('%(asctime)s: %(message)s')
log = logging.getLogger('check-door')
log.setLevel(logging.DEBUG)
logFile = logging.handlers.RotatingFileHandler(appDir + '/logs/check-door.log', maxBytes=100000, backupCount=5)
logFile.setFormatter(logFormat)
log.addHandler(logFile)

# Manage config info
class AppConfig:
    def __init__(self):
        self.configJson = {} 
        configFile = appDir + '/config.json'
        if os.path.isfile(configFile):
            self.configJson = json.loads(open(configFile).read())

    def get(self, key):
        return self.configJson[key]

# Load our previous door state from last time we ran
class AppState:
    def __init__(self):
        self.stateJson = {} 
        self.stateCacheFile = appDir + '/cache/state.json'
        if os.path.isfile(self.stateCacheFile):
            self.stateJson = json.loads(open(self.stateCacheFile).read())

    def get(self, key):
        return self.stateJson[key]

    def set(self, key, value):
        self.stateJson[key] = value

    def isSet(self, key):
        return key in self.stateJson and self.stateJson[key] != None

    def save(self):
        with open(self.stateCacheFile, 'w') as fp:
            json.dump(self.stateJson, fp)

# Load our garage door state from sensor info published to Particle cloud
class DoorState:
    def __init__(self, config):
        self.valid = False
        self.open = False
        try:
            url = config.get('particle.url').format(config.get('particle.device'), config.get('particle.variable'), config.get('particle.token'))
            q = urllib2.urlopen(url)
            gd = q.read()
            q.close()
            self.value = int(gd)

            # Ignore values if too large or small - assume something is wrong with sensor data
            if self.value > 0 and self.value < 10000:
                self.valid = True 
                if self.value > 800:
                    self.open = True
            log.debug('Value: {0}, Valid: {1}, Open: {2}'.format(self.value, self.valid, self.open))
        except Exception as e:
            log.exception("Error getting door value.")

# Logic to post to Slack API: https://api.slack.com/incoming-webhooks#sending_messages
class Slack:
    def __init__(self, config):
        self.config = config

    def send(self, msg):
        try:
            log.debug('Sending message: ' + msg)
            data = 'payload={{"username": "{0}", "text": "{1}"}}'.format(config.get('slack.user'), msg)
            r = urllib2.Request(config.get('slack.url'))
            urllib2.urlopen(r, data)
        except Exception as e:
            log.exception("Error sending message.")

# Load config and door state
config = AppConfig()
door = DoorState(config)

if not door.valid:
    sys.exit() 

# Check previous state 
state = AppState()
openSince = None
if state.isSet('openSince'):
    openSince = dateutil.parser.parse(state.get('openSince'))
    openSinceDisplay = openSince.strftime('%Y-%m-%d %H:%M:%S')
    log.debug("Door has been open since " + openSinceDisplay)

msg = None
if door.open:
    msg = 'Garage door is open.'

    # Flip our state flag to open if it is not already set
    if openSince is None:
        state.set('openSince', now.isoformat())
    else:
        openMinutes = (now - openSince).seconds/60
        if openMinutes > 0:
            msg = "Garage door has been open for " + str(openMinutes) + " minute(s)."

            # If it has been open for more than specified minute threshold also specify @channel
            if openMinutes > config.get('channelNotifyMinutes'):
                msg = "<!channel>: " + msg
else:
    # If door was previously open - clear open state and send a message it is now closed
    if not openSince is None:
        state.set('openSince', None)
        msg = 'Garage door is closed.'

# Send message if we have one to post
if not msg is None:
    slack = Slack(config)
    slack.send(msg)

# Save app state for next time
state.save()

