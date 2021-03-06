#!bin/python

import time
from flask import Flask
from flask import request
import json
import requests
import os
import boto3
from urllib2 import urlopen
import logging
import sys
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from aws_xray_sdk.ext.flask.middleware import XRayMiddleware

portNum = 80

xrayIp = urlopen('http://169.254.169.254/latest/meta-data/public-ipv4').read().decode('utf-8')

app = Flask(__name__)
xray_recorder.configure(
    sampling=True,
    context_missing='LOG_ERROR',
    plugins=('EC2Plugin', 'ECSPlugin'),
    service='iridium',
    daemon_address=xrayIp + ":2000"
)
XRayMiddleware(app, xray_recorder)
patch_all()

# Start a segment
segment = xray_recorder.begin_segment('iridium_general_segment')

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Change this to change the resource
resource = 'iridium'

@xray_recorder.capture()
def produceResource():
    # print "Producing "+resource
    app.logger.info('Producing %s', resource)
    
    #time.sleep(1)
    return

@xray_recorder.capture()
def fulfill(endpoint, number):
    if endpoint == '':
        return 'Missing endpoint'
    else:
        fullEndpoint = 'http://'+str(endpoint)+'/fulfill/'
        data = {resource : number}
        try:
            response = requests.post(fullEndpoint, data=json.dumps(data))
            if response.status_code == requests.codes.ok:
                # print response.status_code
                app.logger.info(response.status_code)
                return response.status_code
            else:
                response.raise_for_status()
        except Exception as e:
            response = e
    return response

# Effectively, our subscriber service.
@app.route('/'+resource+'/', methods=['POST', 'GET'])
def order():
    #This is for health checking
    if request.method == 'GET':
        return 'Welcome to the '+resource+' microservice'
    #Real requests
    elif request.method == 'POST':
        try: 
            # Is this a normal SNS payload? Try to get JSON out of it
            payload = request.get_json(force=True)
            if 'SubscribeURL' in payload:
                app.logger.info('Incoming sub request from SNS...')
                # print 'Incoming subscription request from SNS...'
                # print payload['SubscribeURL']
                # print 'Sending subscription confirmation to SNS...'
                app.logger.info('Sending sub confirmation to SNS...')
                response = requests.get(payload['SubscribeURL'])
                # print response.status_code
                if response.status_code == requests.codes.ok:
                    app.logger.info('SNS topic successfully sucscribed!')
                    return "SNS topic subscribed!"
                else:
                    app.logger.info('There was an issue subscribing to the SNS topic')
                    response.raise_for_status()
            elif (len(json.loads(payload['Message']))) == 1 and resource in payload['Message']:
                app.logger.info('Gathering requested item')
                # print 'Gathering Requested Items'
                produceResource()
                response = fulfill(fulfillmentUrl, 1)
                if response == requests.codes.ok:
                    app.logger.info('%s fulfilled', resource)
                    #print 'Spice fulfilled'
                    return 'Your order has been fulfilled'
                else:
                    #print response
                    app.logger.info(response)
                    return 'Your order has NOT been fulfilled'
            else: 
                app.logger.info('Invalid request JSON. %s was sent', payload['Message'])
                #print 'Invalid Request JSON.'
                #print 'The data sent was %s' % payload['Message']
            
        except Exception as e:
            # Looks like it wasn't.
            # print e
            #print 'This was not a fulfillment request. This microservice is expecting exactly {"'+resource+'": 1}'
            #print 'The data sent was %s' % payload['Message']
            app.logger.error('Something really bad happened. This was definitely not a fulfillment request. Expected {"%s":"1"} but got %s instead', resource, payload['Message'])
            
            return 'We were unable to place your order'
            
        return 'This was not a fulfillment request. This microservice is expecting exactly {"'+resource+'": 1}'
        
    else:
        # We should never get here
        return "This is not the page you are looking for"

#close xray segments
xray_recorder.end_segment()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=portNum)