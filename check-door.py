#!/usr/bin/python3

import datetime
import dateutil.parser    # pip install python-dateutil
import logging
import logging.handlers
import json
import os
import pytz
import requests
import sys
import time

appDir = os.path.dirname(os.path.realpath(sys.argv[0]))
now = datetime.datetime.now()

# Logging
appDir = os.path.dirname(os.path.realpath(sys.argv[0]))
logFormat = logging.Formatter('%(asctime)s: %(message)s')
log = logging.getLogger('check-door')
log.setLevel(logging.DEBUG)
logFile = logging.handlers.RotatingFileHandler(appDir + '/logs/check-door.log', maxBytes=1000000, backupCount=5)
logFile.setFormatter(logFormat)
log.addHandler(logFile)

# Manage config info
class AppConfig:
    def __init__(self):
        self.notify_quiet = False
        self.configJson = {} 
        configFile = appDir + '/config.json'
        if os.path.isfile(configFile):
            self.configJson = json.loads(open(configFile).read())
            self.set_notify_quiet()

    def get(self, key):
        return self.configJson[key]

    def get_minutes_into_day(self, date):
        return (date.hour * 60) + date.minute

    def set_notify_quiet(self):
        now = self.get_minutes_into_day(datetime.datetime.now(pytz.timezone('US/Pacific')))
        start = self.get_minutes_into_day(datetime.datetime.strptime(self.get('notifyQuietStart'), "%H:%M"))
        end = self.get_minutes_into_day(datetime.datetime.strptime(self.get('notifyQuietEnd'), "%H:%M"))
        self.notify_quiet = (now >= start and now <= end)

# Load our previous door state from last time we ran
class AppState:
    def __init__(self):
        self.stateJson = {} 
        self.stateCacheFile = appDir + '/cache/state.json'
        if os.path.isfile(self.stateCacheFile):
            self.stateJson = json.loads(open(self.stateCacheFile).read())

    def get(self, key):
        return self.stateJson[key]

    def getDate(self, key):
        return dateutil.parser.parse(self.stateJson[key])

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
            r = requests.get(url)
            self.value = int(r.text)

            # Ignore values if too large or small - assume something is wrong with sensor data.
            # Value is very consistently in the 200 range when closed.
            if self.value > 0 and self.value < 10000:
                self.valid = True 
                if self.value > 800:
                    self.open = True
            log.debug('Value: {0}, Valid: {1}, Open: {2}'.format(self.value, self.valid, self.open))
        except Exception as e:
            log.exception("Error getting door value.")

        # When debugging it is useful to hard-code the value
        #self.open = True

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
    openSince = state.getDate('openSince')
    openSinceDisplay = openSince.strftime('%Y-%m-%d %H:%M:%S')
    log.debug("Door has been open since " + openSinceDisplay)
        
msg = None
if door.open:
    # Flip our state flag to open if it is not already set
    if openSince is None:
        state.set('openSince', now.isoformat())
        openMinutes = 0
    else:
        openMinutes = (now - openSince).seconds/60

    # Only notify based on our notify interval - this keeps us from sending a Slack message every
    # time the sript runs (lets assume once per minute). 
    sendNotification = True
    if state.isSet('lastOpenNotify'):
        lastOpenNotify = state.getDate('lastOpenNotify')
        sendNotification = ((now - lastOpenNotify).seconds/60) > config.get('notifyIntervalMinutes')
            
    if sendNotification:
        state.set('lastOpenNotify', now.isoformat())
        msg = 'Garage door is open.'
        if openMinutes > 0:
            msg = "Garage door has been open for " + str(openMinutes) + " minute(s)."

            # If it has been open for more than specified minute threshold also specify @channel
            if openMinutes > config.get('notifyChannelMinutes') and not config.notify_quiet:
                msg = "<!channel>: " + msg
    else:
        log.debug("Skipping sending notification due to notification interval.")

else:
    # If door was previously open - clear open state and send a message it is now closed. We always
    # send this message - regardless of notify interval.
    if not openSince is None:
        state.set('openSince', None)
        state.set('lastOpenNotify', None)
        msg = 'Garage door is closed.'

# Send message if we have one to post
if not msg is None:
    slack = Slack(config)
    slack.send(msg)

# Save app state for next time
state.save()

