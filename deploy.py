from __future__ import print_function

import time
import threading
import os
import socket
import sys
import tarfile
import subprocess

from ssh2.session import Session
from datetime import datetime
from functools import partial


class DeploymentProcess():

    def __init__(self, hostname, username, source_workspace, dest_workspace, hex_name, hex_source, hex_dest):
        self.host = hostname
        self.user = username
        self.source_ws = source_workspace
        self.dest_ws = dest_workspace
        self.ws_filename = 'src.tar.gz'
        self.hex_n = hex_name
        self.hex_s = hex_source
        self.hex_d = hex_dest
        self.steps_to_do = -1
        self.steps_done = 0
        self.isDone = False
        self.isFault = False

    def gzip_workspace(self, filename, path):
        compressed_dir = path+"/src/"
        # print("Compressing dir: %s" % path)
        tar = tarfile.open(filename, "w:gz")
        tar.add(compressed_dir,  arcname="src")
        tar.close()

    def upload_file(self, filename, file_path, ssh_session, remote_dir):
        fileinfo = os.stat(file_path + filename)
        file_size = fileinfo.st_size
        counter = 0
        buffer = 0
        buffer_size = 65535
        file_mb = round(file_size/1024/1024, 2)

        chan = ssh_session.scp_send64(remote_dir+filename, fileinfo.st_mode & 0o777,
                                      file_size, fileinfo.st_mtime, fileinfo.st_atime)
        now = datetime.now()

        # print("Uploading %s file with size: %.2f MB" % (filename, file_mb))
        with open(file_path + filename, 'rb', buffering=buffer_size) as local_fh:
            buffer = local_fh.read(buffer_size)
            chan.write(buffer)
            while local_fh.tell() < file_size:
                buffer = local_fh.read(buffer_size)
                chan.write(buffer)
                counter += 1
                if counter % 10 == 0:
                    progress = 100 * (counter * buffer_size) / file_size
                    sent_size = round(counter * buffer_size/1024000, 2)
                    # print("\rSent : %.2f MB = %.2f%%" % (sent_size, progress), end = "")
        # print("\rSent : %.2f MB = %.2f%%   " % (file_mb, 100.0), end="\r\n")
        chan.close()
        taken = datetime.now() - now
        rate = (file_size / (1024000.0)) / taken.total_seconds()
        # print("Finished writing remote file in %s, transfer rate %.2f MB/s" % (taken, round(rate, 2)))

    def start_session(self, hostname, username):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.connect((hostname, 22))
        s = Session()
        s.handshake(sock)
        auth_methods = s.userauth_list(username)
        if 'publickey' in auth_methods:
            s.agent_auth(username)
            return s
        else:
            # print("Available authentiation methods: %s" % auth_methods)
            sys.exit("Only publickey is supported now!")

    def extract_file(self, session, filename, directory):
        command = "tar -zxvf " + directory+filename + " -C " + directory
        # print("Extract command: %s" % command)
        # print("Extracting...", end='')
        channel = session.open_session()
        channel.execute(command)
        size, data = channel.read()
        while size > 0:
            # print(data.decode('utf-8'))
            size, data = channel.read()
        exit_status = channel.get_exit_status()
        channel.close()
        if exit_status == 0:
            # print(" Done")
            return 0
        else:
            sys.exit("Error with file extracting, abort operation!")

    def build_workspace(self, session, workspace):
        command_build_colcon = "colcon build --symlink-install"
        command_build_catkin = "catkin_make"
        command = "(. /opt/ros/kinetic/setup.bash && cd " + \
            workspace + " && " + command_build_catkin + " )"

        # print("Build command: %s" % command)
        # print("Building...")
        channel = session.open_session()
        channel.execute(command)
        size, data = channel.read()
        while size > 0:
            # print(data.decode('utf-8'))
            size, data = channel.read()
        exit_status = channel.get_exit_status()
        # print("Exit status %d" % exit_status)
        channel.close()
        if exit_status == 0:
            # print(" Done")
            return 0
        else:
            sys.exit("Error with build process, abort operation!")

    def isDeploymentDone(self):
        return self.isDone

    def isDeploymentFaulty(self):
        return self.isFault

    def getStepsDone(self):
        return self.steps_done

    def make_deployment(self):
        self.steps_to_do = 6
        # print("Compress local workspace")
        self.gzip_workspace(self.ws_filename, self.source_ws)
        self.steps_done = 1
        # print("Init session")
        self.session = self.start_session(self.host, self.user)
        self.steps_done = 2
        # print("Call upload file")
        self.upload_file(self.ws_filename, "", self.session, self.dest_ws)
        self.steps_done = 3
        # print("Call extract file")
        self.extract_file(self.session, self.ws_filename, self.dest_ws)
        self.steps_done = 4
        # print("Call build workspace")
        self.build_workspace(self.session, self.dest_ws)
        self.steps_done = 5
        # print("Upload hex file")
        self.upload_file(self.hex_n, self.hex_s, self.session, self.hex_d)
        self.steps_done = 6
        self.isDone = True


def deployments_in_progress(deployments):
    in_progress = False
    for d in deployments:
        if not d.isDeploymentDone() and not d.isDeploymentFaulty():
            in_progress = True
    return in_progress


host = "rosbot-office"
user = "husarion"
workspace_to_send = "/home/husarion/ws_to_deploy"
dest_workspace = "/home/husarion/auto_deploy/"
hex_file_location = "/home/husarion/hframewrok_projects/ROSbot_examples/ROSbot_driver/"
hex_file = "myproject.hex"
hex_file_dest = "/home/husarion/"

deployment_one = DeploymentProcess(host, user, workspace_to_send,
                                   dest_workspace, hex_file, hex_file_location, hex_file_dest)
deployment_jobs = [deployment_one]

workThread_deployment_one = threading.Thread(
    target=deployment_one.make_deployment)
workThread_deployment_one.start()

while deployments_in_progress(deployment_jobs):
    time.sleep(0.1)
    print('\rSteps done %5d, Is faulty: %s  ' % (int(deployment_one.getStepsDone()),
                                                 deployment_one.isDeploymentFaulty()), end="")

print('\r\nDone')
