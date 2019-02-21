from __future__ import print_function

import os
import socket
import sys
import tarfile
import subprocess

from ssh2.session import Session
from datetime import datetime
from functools import partial

host = "rosbot-office"
user = "husarion"
workspace_to_send = "/home/husarion/ros_workspace"
source_file = 'src.tar.gz'
dest_workspace = "/home/husarion/auto_deploy/"


def gzip_workspace(filename, path):
    compressed_dir = path+"/src/"
    print("Compressing dir: %s" % path)
    tar = tarfile.open(filename, "w:gz")
    tar.add(compressed_dir,  arcname="src")
    tar.close()


def upload_file(filename, ssh_session, remote_dir):
    fileinfo = os.stat(filename)
    file_size = fileinfo.st_size
    counter = 0
    buffer = 0
    buffer_size = 65535
    file_mb = round(file_size/1024/1024, 2)

    chan = ssh_session.scp_send64(remote_dir+filename, fileinfo.st_mode & 0o777,
                                  file_size, fileinfo.st_mtime, fileinfo.st_atime)
    now = datetime.now()

    print("Uploading %s file with size: %.2f MB" % (filename, file_mb))
    with open(filename, 'rb', buffering=buffer_size) as local_fh:
        buffer = local_fh.read(buffer_size)
        chan.write(buffer)
        while local_fh.tell() < file_size:
            buffer = local_fh.read(buffer_size)
            chan.write(buffer)
            counter += 1
            if counter % 10 == 0:
                progress = 100 * (counter * buffer_size) / file_size
                sent_size = round(counter * buffer_size/1024000, 2)
                print("\rSent : %.2f MB = %.2f%%" %
                      (sent_size, progress), end="")
    print("\rSent : %.2f MB = %.2f%%   " % (file_mb, 100.0), end="\r\n")
    chan.close()
    taken = datetime.now() - now
    rate = (file_size / (1024000.0)) / taken.total_seconds()
    print("Finished writing remote file in %s, transfer rate %.2f MB/s" %
          (taken, round(rate, 2)))


def start_session(hostname, username):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((hostname, 22))
    s = Session()
    s.handshake(sock)
    auth_methods = s.userauth_list(username)
    if 'publickey' in auth_methods:
        s.agent_auth(username)
        return s
    else:
        print("Available authentiation methods: %s" % auth_methods)
        sys.exit("Only publickey is supported now!")


def extract_file(session, filename, directory):
    command = "tar -zxvf " + directory+filename + " -C " + directory
    print("Extract command: %s" % command)
    print("Extracting...", end='')
    channel = session.open_session()
    channel.execute(command)
    size, data = channel.read()
    while size > 0:
        # print(data.decode('utf-8'))
        size, data = channel.read()
    exit_status = channel.get_exit_status()
    channel.close()
    if exit_status == 0:
        print(" Done")
        return 0
    else:
        sys.exit("Error with file extracting, abort operation!")


def build_workspace(session, workspace):
    # command = "(. /opt/ros/kinetic/setup.bash && cd " + dest_workspace + " && colcon build --symlink-install)"
    command = "(. /opt/ros/kinetic/setup.bash && cd " + \
        workspace + " && colcon build --symlink-install)"
    print("Build command: %s" % command)
    print("Building...")
    channel = session.open_session()
    channel.execute(command)
    size, data = channel.read()
    while size > 0:
        print(data.decode('utf-8'))
        size, data = channel.read()
    exit_status = channel.get_exit_status()
    print("Exit status %d" % exit_status)
    channel.close()
    if exit_status == 0:
        print(" Done")
        return 0
    else:
        sys.exit("Error with build process, abort operation!")


print("Compress local workspace")
gzip_workspace(source_file, workspace_to_send)
print("Init session")
session = start_session(host, user)
print("Call upload file")
upload_file(source_file, session, dest_workspace)
print("Call extract file")
extract_file(session, source_file, dest_workspace)
print("Call build workspace")
build_workspace(session, dest_workspace)
