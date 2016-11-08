# garage-door

I wanted my 20 year old garage door to notify me if it was left open by accident. I looked into some of the 3rd party add-ons
but none looked that exciting. 

Instead I hookup up a Particle Photon I had sitting around

## Particle App

There is a simple app running on the photon that exposes the current state of the sensor value to the Particle
cloud. It checks the sensor value every second, averages the value across a short period of time (5 seconds) and
exposes a variable.

```
#define PIRPIN A0

int doorStatus = 0;

void setup() {
    // Setup variable that will be published - this is basically exposing this value to be queried
    // externally when someone comes to check it.
    Particle.variable("garageDoor", doorStatus); 
}
 
void loop() {
    // Get a set of measurements and then avg before reporting.
    int sum = 0;
    int count = 5;
    for(int i = 0; i < count; i += 1) {
        delay(1000);
        sum += analogRead(PIRPIN);
    }
    
    // Set variable value based on avg reading for our time period. 
    doorStatus = sum/count;
}
```

## Notification App

There is then a [Python app](check-door.py) that is scheduled to run once per minute on a Rasbperry PI. It checks the value 
of the variable and publishes notifications to a Slack channel if the door is open and when it is closed.
