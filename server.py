from flask import Flask, render_template, request, jsonify
from flask_cors import CORS, cross_origin
from multiprocessing import Process
import json
import boto3
import time
import paramiko
import os
import io
import warnings

app = Flask(__name__)
CORS(app)

SERVER_NAME = os.getenv('SERVER_NAME', 'On Demand Minecraft Server')
SERVER_ADDRESS = os.getenv('SERVER_ADDRESS')

# Stop paramiko from clogging the log output with depreciation warnings
warnings.filterwarnings(action='ignore', module='.*paramiko.*')

# Paraminko ssh information
key_string = os.getenv('SSH_KEY').replace('\\n', '\n')
key = paramiko.RSAKey.from_private_key(io.StringIO(key_string))
sshClient = paramiko.SSHClient()
sshClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# Waits for the server to reach a valid state so that commands can be executed on the server


def serverWaitOk(client, instanceIp, instanceId):
    checksPassed = False
    status = 'initializing'
    instanceIds = [instanceId]

    print('Waiting for instance', instanceId,
          'to have status ok', flush=True)
    while (not checksPassed) and (status == 'initializing'):
        statusCheckResponse = client.describe_instance_status(
            InstanceIds=instanceIds)
        instanceStatuses = statusCheckResponse['InstanceStatuses']
        instanceStatus = instanceStatuses[0]
        instanceStatus = instanceStatus['InstanceStatus']
        status = instanceStatus['Status']
        checksPassed = status == 'ok'
        print('Instance', instanceId, 'status is', status, flush=True)
        time.sleep(5)

    if checksPassed:
        initServerCommands(instanceIp)
    else:
        print('An error has occurred booting the server', flush=True)

# SSH connects to server and executes command to boot minecraft server


def initServerCommands(instanceIp):
    # Connect/ssh to an instance
    try:
        # Here 'ubuntu' is user name and 'instance_ip' is public IP of EC2
        sshClient.connect(hostname=instanceIp, username="ubuntu", pkey=key)

        _, stdout, _ = sshClient.exec_command("screen -ls | grep minecraft")
        if stdout.read():
            print('Screen already exists. Will not run minecraft again.', flush=True)
            return

        sshClient.exec_command(
            "screen -dmS minecraft bash -c 'sudo java " + os.getenv('MEMORY_ALLOCATION', '') + "-jar server.jar nogui'")
        print('Starting minecraft', flush=True)

        # close the client connection once the job is done
        sshClient.close()

    except Exception as err:
        print('Error running server commands:')
        print(err, flush=True)

def render_index(**vargs):
    return render_template('index.html', serverName=SERVER_NAME, serverAddress=SERVER_ADDRESS, **vargs)

# Main endpoint for loading the webpage


@app.route('/')
def loadIndex():
    return render_index()


@app.route('/initServerMC', methods=['POST'])
def initServerMC():
    inputPass = request.form['pass']

    message = "Password Incorrect!"

    if inputPass == os.getenv('SERVER_PASSWORD'):
        print('IP', request.remote_addr,
              'has supplied correct password', flush=True)
        # Instantiate server here or return ip address if already running
        client = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('ACCESS_KEY'),
            aws_secret_access_key=os.getenv('SECRET_KEY'),
            region_name=os.getenv('EC2_REGION')
        )
        message = manageServer(client)
    else:
        print('IP', request.remote_addr,
              'gave wrong password \'{}\''.format(inputPass), flush=True)

    return render_index(ipMessage=message)


# Gets IP Address for return to webpage otherwise boots server
def manageServer(client):
    returnString = 'ERROR'

    instanceIds = [os.getenv('INSTANCE_ID')]
    response = client.describe_instances(InstanceIds=instanceIds)
    reservations = response['Reservations']
    reservation = reservations[0]

    instances = reservation['Instances']

    if len(instances) > 0:
        instance = instances[0]
        print('Found instance with id', instance['InstanceId'], flush=True)
        state = instance['State']
        stateName = state['Name']

        if (stateName == 'stopped') or (stateName == 'shutting-down'):
            returnString = startServer(client, instance['InstanceId'])
        elif stateName == 'running':
            # Restart minecraft if needed
            initServerCommands(instance['PublicIpAddress'])
            returnString = 'Server is up and running!'
        else:
            print('Instance state \'{}\' is unrecognized'.format(
                stateName), flush=True)
            returnString = 'Server is in an unrecognized state, please try again in a few minutes'
    return returnString

# Starts the specified AWS Instance from the configuration


def startServer(client, instanceId):
    # Gets proper variables to attempt to instantiate EC2 instance and start minecraft server
    returnString = 'ERROR'
    instanceIds = [instanceId]
    response = client.start_instances(InstanceIds=instanceIds)
    print('AWS EC2 START RESPONSE\n')
    print(response)
    print('\n', flush=True)

    stateCode = 0

    while not (stateCode == 16):
        print('Waiting for instance', instanceId, 'to start', flush=True)
        time.sleep(3)

        response = client.describe_instances(InstanceIds=instanceIds)
        reservations = response['Reservations']
        reservation = reservations[0]

        instances = reservation['Instances']
        instance = instances[0]

        state = instance['State']
        stateCode = state['Code']

    ipAddress = instance['PublicIpAddress']
    returnString = 'Server is starting, this may take a few minutes... Remember to hit refresh in Minecraft!'
    # SETUP MULTIPROCESSING HERE INSTEAD OF REDIS
    p = Process(target=serverWaitOk, args=(client, ipAddress, instanceId))
    p.start()
    return returnString


if __name__ == "__main__":
    app.run()
