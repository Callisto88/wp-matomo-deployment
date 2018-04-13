# ssh = paramiko.SSHClient()
# ssh.load_system_host_keys()
# ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
# ssh_stdin = ssh_stdout = ssh_stderr = None

#try:
 #   ssh.connect(server, username="", password="")

    #channel = ssh.invoke_shell()
    #channel.send('su -\n')
    #while not channel.recv_ready():
    #    time.sleep(1)
    #print
    #channel.recv(1024)
    #channel.send('*******\n')
    #while not channel.recv_ready():
    #    time.sleep(1)
    #print
    #channel.recv(1024)

#    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)
#except Exception as e:
#    sys.stderr.write("SSH connection error: {0}".format(e))


#for line in ssh_stdout:
#    print('... ' + line.strip('\n'))

#for line in ssh_stderr:
#    print('... ' + line.strip('\n'))